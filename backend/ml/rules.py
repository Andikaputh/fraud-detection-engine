"""Deterministic rule layer.

Rules encode policies an analyst can explain to a customer or a regulator. They
run alongside the model, not instead of it: the model catches unfamiliar patterns,
the rules enforce thresholds and invariants. Each hit carries a weight that is
shown in the console so a decision is never a black box.
"""

from __future__ import annotations

from typing import Any


def _idr(value: float) -> str:
    return f"Rp {value:,.0f}".replace(",", ".")


def build_reasons(event: dict[str, Any], meta: dict[str, Any], cfg: dict[str, Any]) -> list[dict]:
    reasons: list[dict] = []
    amount = float(event["amount"])
    if amount >= cfg["amount_sensitivity"]:
        reasons.append(
            {
                "code": "AMOUNT_ABOVE_THRESHOLD",
                "label": "Amount above review threshold",
                "weight": 35,
                "detail": f"{_idr(amount)} exceeds the configured {_idr(cfg['amount_sensitivity'])} limit.",
            }
        )

    if meta["amount_ratio"] >= 8 and amount >= 1_000_000:
        reasons.append(
            {
                "code": "AMOUNT_RATIO_EXTREME",
                "label": "Spend far above customer baseline",
                "weight": 32,
                "detail": (
                    f"Ticket is {meta['amount_ratio']:.0f}x the customer's average spend "
                    f"({_idr(meta['avg_amount'])})."
                ),
            }
        )

    if meta["velocity_1m"] >= cfg["velocity_limit_1m"]:
        reasons.append(
            {
                "code": "VELOCITY_1M",
                "label": "High one-minute velocity",
                "weight": 30,
                "detail": f"{meta['velocity_1m']} authorisations on this card within 60 seconds.",
            }
        )

    if meta["velocity_10m"] >= cfg["velocity_limit_10m"]:
        reasons.append(
            {
                "code": "VELOCITY_10M",
                "label": "Sustained velocity",
                "weight": 22,
                "detail": f"{meta['velocity_10m']} authorisations within 10 minutes.",
            }
        )

    if meta["velocity_1m"] >= 4 and meta["amount_ratio"] < 0.5 and amount < 250_000:
        reasons.append(
            {
                "code": "CARD_TESTING",
                "label": "Card-testing pattern",
                "weight": 30,
                "detail": "Rapid sequence of low-value authorisations, typical of card enumeration.",
            }
        )

    if meta["geo_distance_km"] > 50 and meta["geo_speed_kmh"] > 900:
        reasons.append(
            {
                "code": "IMPOSSIBLE_TRAVEL",
                "label": "Impossible travel",
                "weight": 28,
                "detail": (
                    f"{meta['geo_distance_km']:,.0f} km from the previous merchant at an implied "
                    f"{meta['geo_speed_kmh']:,.0f} km/h."
                ).replace(",", "."),
            }
        )

    if meta["new_device"] and (meta["amount_ratio"] >= 2.5 or amount >= 2_000_000):
        reasons.append(
            {
                "code": "NEW_DEVICE_HIGH_VALUE",
                "label": "New device with elevated value",
                "weight": 24,
                "detail": "First time this device is seen for the customer on a high-value authorisation.",
            }
        )

    if meta["amount_z"] >= 3:
        reasons.append(
            {
                "code": "AMOUNT_DEVIATION",
                "label": "Amount deviates from history",
                "weight": 22,
                "detail": f"{meta['amount_z']:.1f} standard deviations above the customer's typical ticket.",
            }
        )

    if meta["merchant_risk"] >= 0.6:
        reasons.append(
            {
                "code": "HIGH_RISK_MERCHANT",
                "label": "High-risk merchant category",
                "weight": 18,
                "detail": "Merchant category carries elevated chargeback exposure.",
            }
        )

    if meta["ip_mismatch"]:
        reasons.append(
            {
                "code": "IP_COUNTRY_MISMATCH",
                "label": "IP country mismatch",
                "weight": 14,
                "detail": "IP geolocation matches neither the merchant country nor the customer's home country.",
            }
        )

    if meta["local_hour"] <= 5:
        reasons.append(
            {
                "code": "UNUSUAL_HOUR",
                "label": "Outside normal hours",
                "weight": 8,
                "detail": f"Authorisation at {meta['local_hour']:02d}:00 local time.",
            }
        )

    if meta["account_age_days"] < 7:
        reasons.append(
            {
                "code": "NEW_ACCOUNT",
                "label": "Recently created account",
                "weight": 10,
                "detail": f"Account is {meta['account_age_days']} day(s) old.",
            }
        )

    if meta["chargebacks"] > 0:
        reasons.append(
            {
                "code": "CHARGEBACK_HISTORY",
                "label": "Prior chargebacks",
                "weight": 12,
                "detail": f"{meta['chargebacks']} previous chargeback(s) on the customer profile.",
            }
        )

    if meta["disposable_email"]:
        reasons.append(
            {
                "code": "DISPOSABLE_EMAIL",
                "label": "Disposable email domain",
                "weight": 12,
                "detail": "Customer email uses a known temporary-mail provider.",
            }
        )

    if meta["distinct_countries_24h"] >= 3:
        reasons.append(
            {
                "code": "MULTI_COUNTRY_24H",
                "label": "Multiple countries in 24h",
                "weight": 15,
                "detail": f"Transactions from {meta['distinct_countries_24h']} countries in the last day.",
            }
        )

    reasons.sort(key=lambda item: item["weight"], reverse=True)
    return reasons
