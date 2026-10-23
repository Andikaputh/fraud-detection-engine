"""Feature engineering for the risk engine.

Every feature is computed from data available before the authorisation decision
is returned. State is kept in memory per customer and per card so the hot path
does not need a database round-trip; the same state warms up on boot from the
persisted transaction tail.

The feature vector is versioned through `FEATURE_NAMES`. Changing it without
retraining the model will be rejected by the scorer's shape check.
"""

from __future__ import annotations

import math
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from backend.core.geo import coords_for, haversine_km

FEATURE_NAMES = [
    "log_amount",
    "log_amount_ratio",
    "amount_z",
    "velocity_1m",
    "velocity_10m",
    "log_geo_speed",
    "new_device",
    "hour_sin",
    "hour_cos",
    "merchant_risk",
    "ip_country_mismatch",
    "channel_risk",
    "log_account_age",
    "chargebacks",
    "distinct_countries_24h",
    "is_disposable_email",
]

CHANNEL_RISK = {
    "ecommerce": 0.55,
    "pos": 0.2,
    "atm": 0.35,
    "transfer": 0.6,
    "subscription": 0.3,
}

COUNTRY_OFFSETS = {
    "ID": 7,
    "SG": 8,
    "MY": 8,
    "TH": 7,
    "PH": 8,
    "VN": 7,
    "AU": 10,
    "JP": 9,
    "CN": 8,
    "RU": 3,
    "NG": 1,
    "BR": -3,
    "US": -6,
    "GB": 0,
    "IN": 5,
}

DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com",
    "tempmail.com",
    "guerrillamail.com",
    "10minutemail.com",
    "yopmail.com",
    "trashmail.com",
    "sharklasers.com",
}

HIGH_RISK_CATEGORIES = {
    "crypto": 0.9,
    "gift_cards": 0.82,
    "jewelry": 0.6,
    "gaming": 0.55,
    "electronics": 0.45,
    "travel": 0.38,
    "fashion": 0.25,
    "marketplace": 0.2,
}


@dataclass
class CardState:
    timestamps: deque[datetime] = field(default_factory=lambda: deque(maxlen=64))
    last_country: str | None = None
    last_time: datetime | None = None
    devices: set[str] = field(default_factory=set)
    countries: deque[tuple[datetime, str]] = field(default_factory=lambda: deque(maxlen=64))


@dataclass
class CustomerState:
    amount_count: int = 0
    amount_sum: float = 0.0
    log_sum: float = 0.0
    log_sq_sum: float = 0.0
    devices: set[str] = field(default_factory=set)
    countries: deque[tuple[datetime, str]] = field(default_factory=lambda: deque(maxlen=128))
    chargebacks: int = 0
    account_age_days: int = 365
    home_country: str | None = None


class FeatureStore:
    """In-memory entity graph used to derive velocity and deviation features."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cards: dict[str, CardState] = defaultdict(CardState)
        self._customers: dict[str, CustomerState] = defaultdict(CustomerState)

    def build(self, event: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
        customer_id = event["customer_id"]
        card_key = event.get("card_id") or customer_id
        now: datetime = event["created_at"]
        amount: float = event["amount"]
        merchant_country = (event.get("merchant_country") or "ID").upper()
        ip_country = (event.get("ip_country") or merchant_country).upper()
        context = event.get("context") or {}

        with self._lock:
            card = self._cards[card_key]
            customer = self._customers[customer_id]

            cutoff_10m = now - timedelta(minutes=10)
            while card.timestamps and card.timestamps[0] < cutoff_10m:
                card.timestamps.popleft()

            velocity_10m = sum(1 for ts in card.timestamps if ts >= now - timedelta(minutes=10)) + 1
            velocity_1m = sum(1 for ts in card.timestamps if ts >= now - timedelta(minutes=1)) + 1

            if customer.amount_count:
                avg_amount = customer.amount_sum / customer.amount_count
                mean_log = customer.log_sum / customer.amount_count
                variance = max(customer.log_sq_sum / customer.amount_count - mean_log**2, 1e-6)
                std_log = math.sqrt(variance)
            else:
                avg_amount = float(context.get("avg_amount") or amount)
                mean_log = math.log1p(avg_amount)
                std_log = 0.0

            log_amount = math.log1p(amount)
            amount_ratio = amount / max(avg_amount, 1.0)
            amount_z = (log_amount - mean_log) / std_log if customer.amount_count >= 4 and std_log > 0.05 else 0.0

            previous_coords = coords_for(card.last_country)
            current_coords = coords_for(merchant_country)
            distance_km = haversine_km(previous_coords, current_coords) if card.last_country else 0.0
            speed_kmh = 0.0
            if card.last_time and card.last_country and merchant_country != card.last_country:
                elapsed_h = max((now - card.last_time).total_seconds() / 3600.0, 1 / 60)
                speed_kmh = distance_km / elapsed_h
            if card.last_country == merchant_country:
                distance_km = 0.0

            new_device = bool(event.get("device_id")) and event["device_id"] not in customer.devices
            account_age_days = int(context.get("account_age_days", customer.account_age_days))
            chargebacks = int(context.get("chargebacks", customer.chargebacks))
            email_domain = (event.get("email_domain") or "").lower()
            is_disposable = email_domain in DISPOSABLE_EMAIL_DOMAINS
            home_country = (context.get("home_country") or customer.home_country or merchant_country).upper()
            ip_mismatch = bool(ip_country and ip_country != merchant_country and ip_country != home_country)

            cutoff_24h = now - timedelta(hours=24)
            while customer.countries and customer.countries[0][0] < cutoff_24h:
                customer.countries.popleft()
            distinct_countries_24h = len({c for _, c in customer.countries} | {merchant_country})

            merchant_risk = float(event.get("merchant_risk") or HIGH_RISK_CATEGORIES.get(event.get("merchant_category", ""), 0.15))
            channel_risk = CHANNEL_RISK.get(event.get("channel", "ecommerce"), 0.5)
            local_hour = (now.hour + COUNTRY_OFFSETS.get(merchant_country, 0)) % 24
            hour_sin = math.sin(2 * math.pi * local_hour / 24)
            hour_cos = math.cos(2 * math.pi * local_hour / 24)

            features = {
                "log_amount": log_amount,
                "log_amount_ratio": math.log1p(max(amount_ratio, 0)),
                "amount_z": max(-6.0, min(12.0, amount_z)),
                "velocity_1m": float(velocity_1m),
                "velocity_10m": float(velocity_10m),
                "log_geo_speed": math.log1p(speed_kmh),
                "new_device": 1.0 if new_device else 0.0,
                "hour_sin": hour_sin,
                "hour_cos": hour_cos,
                "merchant_risk": merchant_risk,
                "ip_country_mismatch": 1.0 if ip_mismatch else 0.0,
                "channel_risk": channel_risk,
                "log_account_age": math.log1p(max(account_age_days, 0)),
                "chargebacks": float(chargebacks),
                "distinct_countries_24h": float(distinct_countries_24h),
                "is_disposable_email": 1.0 if is_disposable else 0.0,
            }

            meta = {
                "velocity_1m": velocity_1m,
                "velocity_10m": velocity_10m,
                "amount_ratio": round(amount_ratio, 2),
                "amount_z": round(amount_z, 2),
                "avg_amount": round(avg_amount, 2),
                "new_device": new_device,
                "geo_distance_km": round(distance_km, 1),
                "geo_speed_kmh": round(speed_kmh, 1),
                "local_hour": local_hour,
                "merchant_risk": round(merchant_risk, 2),
                "ip_mismatch": ip_mismatch,
                "home_country": home_country,
                "account_age_days": account_age_days,
                "chargebacks": chargebacks,
                "distinct_countries_24h": distinct_countries_24h,
                "disposable_email": is_disposable,
                "tx_count": customer.amount_count,
            }

            # Update state only after the features are derived.
            card.timestamps.append(now)
            card.last_country = merchant_country
            card.last_time = now
            card.countries.append((now, merchant_country))
            if event.get("device_id"):
                card.devices.add(event["device_id"])
            if event.get("device_id"):
                customer.devices.add(event["device_id"])
            customer.amount_count += 1
            customer.amount_sum += amount
            customer.log_sum += log_amount
            customer.log_sq_sum += log_amount**2
            customer.countries.append((now, merchant_country))
            if context.get("home_country"):
                customer.home_country = context["home_country"].upper()
            if context.get("account_age_days") is not None:
                customer.account_age_days = int(context["account_age_days"])
            if context.get("chargebacks") is not None:
                customer.chargebacks = int(context["chargebacks"])

            return features, meta

    def clear(self) -> None:
        with self._lock:
            self._cards.clear()
            self._customers.clear()

    def warm(self, rows: list[dict[str, Any]]) -> None:
        """Rebuild state from recent transactions without scoring them."""
        for row in rows:
            try:
                self.build(row)
            except Exception:
                continue
