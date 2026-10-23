"""Synthetic transaction world.

The generator is the only part of the system that knows the ground truth. It
models 400 recurring customers, 36 merchants and four fraud archetypes so the
console has realistic entity history, velocity, cross-border behaviour and an
honest review queue instead of pure random amounts.
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from backend.ml.features import HIGH_RISK_CATEGORIES

FRAUD_IP_COUNTRIES = ["RU", "CN", "NG", "US", "BR", "VN"]
LOCAL_COUNTRIES = ["ID", "ID", "ID", "ID", "ID", "ID", "ID", "SG", "MY"]


@dataclass(frozen=True)
class Merchant:
    id: str
    name: str
    category: str
    country: str
    risk_tier: float
    ticket: float


@dataclass
class Customer:
    id: str
    card_id: str
    home_country: str
    city: str
    avg_amount: float
    account_age_days: int
    chargebacks: int
    devices: list[str]
    email_domain: str
    preferred_merchants: list[str] = field(default_factory=list)

    def known_device(self) -> str:
        return random.choice(self.devices)


def _merchant(id_: str, name: str, category: str, country: str, ticket: float) -> Merchant:
    return Merchant(
        id=id_,
        name=name,
        category=category,
        country=country,
        risk_tier=HIGH_RISK_CATEGORIES.get(category, 0.15),
        ticket=ticket,
    )


MERCHANTS: list[Merchant] = [
    _merchant("mrc_01", "TokoBara Elektronik", "electronics", "ID", 2_400_000),
    _merchant("mrc_02", "Nusantara Travel", "travel", "ID", 3_800_000),
    _merchant("mrc_03", "Aurora Jewelry", "jewelry", "ID", 4_500_000),
    _merchant("mrc_04", "SwiftMart", "grocery", "ID", 180_000),
    _merchant("mrc_05", "Kopi Kita", "food", "ID", 55_000),
    _merchant("mrc_06", "LintasPay Crypto", "crypto", "SG", 8_000_000),
    _merchant("mrc_07", "GiftHub Global", "gift_cards", "US", 1_200_000),
    _merchant("mrc_08", "PixelPlay Games", "gaming", "SG", 320_000),
    _merchant("mrc_09", "RideNow", "transport", "ID", 48_000),
    _merchant("mrc_10", "Sinar Fashion", "fashion", "ID", 420_000),
    _merchant("mrc_11", "Andalan Furniture", "furniture", "ID", 2_800_000),
    _merchant("mrc_12", "Medika Pharmacy", "pharmacy", "ID", 130_000),
    _merchant("mrc_13", "StreamNusa", "streaming", "ID", 89_000),
    _merchant("mrc_14", "Bumi Fuel", "fuel", "ID", 250_000),
    _merchant("mrc_15", "Pasar Raya Online", "marketplace", "ID", 260_000),
    _merchant("mrc_16", "Orbit Electronics SG", "electronics", "SG", 3_100_000),
    _merchant("mrc_17", "Kuala Gadget", "electronics", "MY", 2_200_000),
    _merchant("mrc_18", "Pacific Travel Hub", "travel", "SG", 4_200_000),
    _merchant("mrc_19", "Golden Vault", "crypto", "MY", 9_000_000),
    _merchant("mrc_20", "QuickGames", "gaming", "MY", 240_000),
    _merchant("mrc_21", "Harbour Duty Free", "fashion", "SG", 950_000),
    _merchant("mrc_22", "Selera Nusantara", "food", "ID", 75_000),
    _merchant("mrc_23", "Tirta Utilities", "utilities", "ID", 310_000),
    _merchant("mrc_24", "Cahaya Optik", "pharmacy", "ID", 480_000),
    _merchant("mrc_25", "Rumah Kita", "furniture", "ID", 1_900_000),
    _merchant("mrc_26", "MegaGift Store", "gift_cards", "ID", 600_000),
    _merchant("mrc_27", "Urban Sneakers", "fashion", "ID", 1_100_000),
    _merchant("mrc_28", "Delta Air", "travel", "SG", 5_600_000),
    _merchant("mrc_29", "CryptoBridge", "crypto", "US", 12_000_000),
    _merchant("mrc_30", "LuckySpin", "gaming", "PH", 150_000),
    _merchant("mrc_31", "BrightMart", "grocery", "MY", 210_000),
    _merchant("mrc_32", "Hotel Cendana", "travel", "ID", 1_600_000),
    _merchant("mrc_33", "GadgetZone", "electronics", "ID", 1_800_000),
    _merchant("mrc_34", "Toko Emas Mulia", "jewelry", "ID", 6_200_000),
    _merchant("mrc_35", "CloudBox Storage", "utilities", "SG", 120_000),
    _merchant("mrc_36", "Jaya Sport", "fashion", "ID", 780_000),
]

MERCHANT_BY_ID = {merchant.id: merchant for merchant in MERCHANTS}
RISKY_MERCHANTS = [m for m in MERCHANTS if m.risk_tier >= 0.45]
LOCAL_MERCHANTS = [m for m in MERCHANTS if m.country == "ID"]

ANALYSTS = ["a.nugroho", "s.rahman", "d.pratama", "k.wijaya"]

EMAIL_DOMAINS = [
    "gmail.com",
    "gmail.com",
    "gmail.com",
    "yahoo.co.id",
    "outlook.com",
    "icloud.com",
    "proton.me",
    "mailinator.com",
    "tempmail.com",
]


class World:
    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)
        self.customers: list[Customer] = self._build_customers()

    def _build_customers(self) -> list[Customer]:
        rng = self.rng
        customers: list[Customer] = []
        for index in range(400):
            country = rng.choice(LOCAL_COUNTRIES)
            city = rng.choice(["Jakarta", "Surabaya", "Bandung", "Medan", "Denpasar"])
            if country != "ID":
                city = "Singapore" if country == "SG" else "Kuala Lumpur"
            avg_amount = float(min(max(rng.lognormvariate(11.6, 0.8), 25_000), 3_500_000))
            account_age = int(min(rng.expovariate(1 / 420), 3650))
            if rng.random() < 0.06:
                account_age = rng.randint(1, 6)
            chargebacks = 0
            if rng.random() < 0.035:
                chargebacks = rng.randint(1, 2)
            customers.append(
                Customer(
                    id=f"cus_{index + 1:04d}",
                    card_id=f"card_{rng.randrange(16**8):08x}",
                    home_country=country,
                    city=city,
                    avg_amount=avg_amount,
                    account_age_days=account_age,
                    chargebacks=chargebacks,
                    devices=[f"dev_{rng.randrange(16**10):010x}" for _ in range(rng.choice([1, 1, 1, 2]))],
                    email_domain=rng.choice(EMAIL_DOMAINS),
                    preferred_merchants=[m.id for m in rng.sample(LOCAL_MERCHANTS, k=3)],
                )
            )
        return customers

    # ------------------------------------------------------------------ normal
    def normal_event(self, timestamp: datetime, high_value: bool = False) -> dict:
        rng = self.rng
        customer = rng.choice(self.customers)
        if rng.random() < 0.8:
            merchant = MERCHANT_BY_ID[rng.choice(customer.preferred_merchants)]
        else:
            merchant = rng.choice(MERCHANTS if rng.random() < 0.2 else LOCAL_MERCHANTS)

        amount = max(15_000.0, rng.lognormvariate(math.log(customer.avg_amount), 0.55))
        if high_value:
            amount = max(amount, rng.uniform(5_500_000, 16_000_000))
        else:
            amount = min(amount, 4_500_000)

        return self._payload(
            customer=customer,
            merchant=merchant,
            amount=round(amount, 2),
            timestamp=timestamp,
            device=customer.known_device(),
            ip_country=customer.home_country,
            label="legit",
            high_value=high_value,
        )

    # ------------------------------------------------------------------- fraud
    def fraud_event(self, timestamp: datetime, pattern: str | None = None) -> dict:
        rng = self.rng
        pattern = pattern or rng.choices(
            ["stolen_card", "account_takeover", "card_testing"],
            weights=[0.42, 0.33, 0.25],
        )[0]
        customer = rng.choice(self.customers)

        if pattern == "card_testing":
            merchant = rng.choice([m for m in MERCHANTS if m.risk_tier < 0.5])
            amount = round(rng.uniform(20_000, 240_000), 2)
        elif pattern == "account_takeover":
            merchant = rng.choice([m for m in MERCHANTS if m.country != "ID"] + RISKY_MERCHANTS)
            amount = round(rng.uniform(3_000_000, 24_000_000), 2)
        else:  # stolen_card
            merchant = rng.choice(RISKY_MERCHANTS)
            amount = round(rng.uniform(8_000_000, 48_000_000), 2)

        return self._payload(
            customer=customer,
            merchant=merchant,
            amount=amount,
            timestamp=timestamp,
            device=f"dev_{uuid.uuid4().hex[:10]}",
            ip_country=rng.choice(FRAUD_IP_COUNTRIES),
            label="fraud",
            pattern=pattern,
        )

    # ------------------------------------------------------------------ bursts
    def card_testing_burst(self, start: datetime, count: int) -> list[dict]:
        customer = self.rng.choice(self.customers)
        merchant = self.rng.choice([m for m in MERCHANTS if m.risk_tier < 0.5])
        device = f"dev_{uuid.uuid4().hex[:10]}"
        events = []
        for index in range(count):
            events.append(
                self._payload(
                    customer=customer,
                    merchant=merchant,
                    amount=round(self.rng.uniform(18_000, 190_000), 2),
                    timestamp=start + timedelta(seconds=index * 3),
                    device=device,
                    ip_country=self.rng.choice(FRAUD_IP_COUNTRIES),
                    label="fraud",
                    pattern="card_testing",
                )
            )
        return events

    def burst(self, pattern: str, count: int, start: datetime | None = None) -> list[dict]:
        start = start or datetime.utcnow()
        if pattern == "card_testing":
            return self.card_testing_burst(start, count)
        if pattern == "mixed":
            return [
                self.fraud_event(start + timedelta(seconds=index), None)
                for index in range(count)
            ]
        return [
            self.fraud_event(start + timedelta(seconds=index), pattern)
            for index in range(count)
        ]

    # ------------------------------------------------------------- historical
    def history(self, count: int, days: int = 7) -> list[dict]:
        """Chronologically ordered labelled history used to seed a fresh install."""
        rng = random.Random(self.rng.random())
        now = datetime.utcnow().replace(microsecond=0)
        start = now - timedelta(days=days)
        events: list[dict] = []
        for _ in range(count):
            # Diurnal weighting: retail volume troughs overnight and ramps back
            # after dawn. A hard cutoff creates an artificial step in the hourly
            # chart, so use a gradual 55% -> 90% curve before 06:00 local.
            while True:
                offset = timedelta(seconds=rng.randrange(max(days * 86_400 - 60, 1)))
                candidate = start + offset
                local_hour = (candidate.hour + 7) % 24
                weight = 0.55 + 0.07 * local_hour if local_hour < 6 else 1.0
                if rng.random() < weight:
                    break
            roll = rng.random()
            if roll < 0.028:
                events.append(self.fraud_event(candidate))
            elif roll < 0.031:
                burst_start = candidate
                events.extend(self.card_testing_burst(burst_start, rng.randint(6, 11)))
            elif roll < 0.055:
                events.append(self.normal_event(candidate, high_value=True))
            else:
                events.append(self.normal_event(candidate))
        events.sort(key=lambda item: item["timestamp"])
        return events

    # ---------------------------------------------------------------- payload
    def _payload(
        self,
        customer: Customer,
        merchant: Merchant,
        amount: float,
        timestamp: datetime,
        device: str,
        ip_country: str,
        label: str,
        pattern: str | None = None,
        high_value: bool = False,
    ) -> dict:
        return {
            "transaction_id": f"txn_{uuid.uuid4().hex[:16]}",
            "external_id": f"ord_{self.rng.randrange(10**9, 10**10)}",
            "customer_id": customer.id,
            "card_id": customer.card_id,
            "amount": amount,
            "currency": "IDR",
            "merchant": {
                "id": merchant.id,
                "name": merchant.name,
                "category": merchant.category,
                "country": merchant.country,
                "risk_tier": merchant.risk_tier,
            },
            "channel": self.rng.choices(
                ["ecommerce", "pos", "atm", "transfer", "subscription"],
                weights=[0.62, 0.16, 0.04, 0.1, 0.08],
            )[0],
            "device_id": device,
            "ip_country": ip_country,
            "email": f"user{customer.id[-4:]}@{customer.email_domain}",
            "timestamp": timestamp,
            "context": {
                "home_country": customer.home_country,
                "account_age_days": customer.account_age_days,
                "chargebacks": customer.chargebacks,
                "avg_amount": round(customer.avg_amount, 2),
            },
            "label": label,
            "pattern": pattern,
            "high_value": high_value,
        }
