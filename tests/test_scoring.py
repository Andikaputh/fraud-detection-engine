from __future__ import annotations

from datetime import timedelta

from backend.core.timeutil import utcnow
from backend.ml.features import FEATURE_NAMES, FeatureStore


def _event(customer: str, card: str, amount: float, when, device: str = "dev_a", country: str = "ID"):
    return {
        "customer_id": customer,
        "card_id": card,
        "amount": amount,
        "merchant_country": country,
        "merchant_category": "electronics",
        "merchant_risk": 0.4,
        "channel": "ecommerce",
        "device_id": device,
        "ip_country": country,
        "email_domain": "gmail.com",
        "created_at": when,
        "context": {"home_country": "ID", "account_age_days": 200, "chargebacks": 0, "avg_amount": 200_000},
    }


def test_feature_contract_is_stable():
    store = FeatureStore()
    features, meta = store.build(_event("cus_1", "card_1", 150_000, utcnow()))
    assert list(features.keys()) == FEATURE_NAMES
    assert meta["velocity_1m"] == 1
    assert meta["new_device"] is True


def test_velocity_and_amount_deviation_accumulate():
    store = FeatureStore()
    now = utcnow()
    baseline = [100_000, 110_000, 90_000, 105_000, 95_000]
    for index, amount in enumerate(baseline):
        store.build(_event("cus_2", "card_2", amount, now - timedelta(minutes=30 - index)))

    features, meta = store.build(_event("cus_3", "card_3", 100_000, now - timedelta(seconds=20)))
    _, meta2 = store.build(_event("cus_3", "card_3", 100_000, now - timedelta(seconds=10)))
    _, meta3 = store.build(_event("cus_3", "card_3", 100_000, now))
    assert meta3["velocity_1m"] == 3
    assert features["log_amount"] > 0

    _, outlier = store.build(_event("cus_2", "card_2", 9_000_000, now))
    assert outlier["amount_z"] > 2


def test_new_device_detection():
    store = FeatureStore()
    now = utcnow()
    _, first = store.build(_event("cus_4", "card_4", 120_000, now - timedelta(minutes=5), device="dev_known"))
    _, second = store.build(_event("cus_4", "card_4", 120_000, now, device="dev_known"))
    _, third = store.build(_event("cus_4", "card_4", 120_000, now, device="dev_new"))
    assert first["new_device"] is True
    assert second["new_device"] is False
    assert third["new_device"] is True


def test_scorer_blocks_obvious_fraud():
    from backend.core.settings_store import get_engine_config
    from backend.ml.scorer import get_scorer

    store = FeatureStore()
    now = utcnow()
    event = _event("cus_5", "card_5", 40_000_000, now, device="dev_fraud", country="SG")
    event["ip_country"] = "RU"
    features, meta = store.build(event)
    result = get_scorer().assess(event, features, meta, get_engine_config())
    assert result["risk_score"] >= 80
    assert result["decision"] == "block"
    assert result["reasons"]
