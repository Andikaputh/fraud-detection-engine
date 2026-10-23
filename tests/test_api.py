from __future__ import annotations

import time
import uuid
from datetime import datetime

from backend.api.runtime import runtime


def _payload(amount: float = 250_000, **overrides):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "customer_id": f"cus_test_{suffix}",
        "card_id": f"card_test_{suffix}",
        "amount": amount,
        "merchant": {
            "id": "mrc_test",
            "name": "Test Merchant",
            "category": "electronics",
            "country": "ID",
            "risk_tier": 0.45,
        },
        "channel": "ecommerce",
        "device_id": f"dev_test_{suffix}",
        "ip_country": "ID",
        "email": "tester@example.com",
        "context": {"home_country": "ID", "account_age_days": 400, "chargebacks": 0, "avg_amount": 200_000},
    }
    payload.update(overrides)
    return payload


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_version"]


def test_ingest_scores_transaction(client):
    response = client.post("/api/v1/transactions", json=_payload())
    assert response.status_code == 200
    body = response.json()
    transaction = body["transaction"]
    assert transaction["amount"] == 250_000
    assert 0 <= transaction["risk_score"] <= 100
    assert transaction["decision"] in {"allow", "review", "block"}
    assert transaction["latency_ms"] < 100


def test_high_value_transaction_is_flagged(client):
    response = client.post("/api/v1/transactions", json=_payload(amount=42_000_000))
    assert response.status_code == 200
    body = response.json()
    assert body["transaction"]["decision"] == "block"
    assert body["transaction"]["risk_score"] >= 80
    assert body["alert"] is not None
    codes = {reason["code"] for reason in body["transaction"]["reasons"]}
    assert "AMOUNT_ABOVE_THRESHOLD" in codes


def test_what_if_reports_reasons(client):
    response = client.post(
        "/api/v1/model/score",
        json={
            "amount": 18_000_000,
            "merchant_category": "crypto",
            "merchant_country": "SG",
            "ip_country": "RU",
            "channel": "ecommerce",
            "new_customer": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk_score"] > 40
    assert body["reasons"]
    assert "features" in body


def test_transaction_and_alert_flow(client):
    created = client.post("/api/v1/transactions", json=_payload(amount=35_000_000)).json()
    transaction_id = created["transaction"]["id"]
    alert_id = created["alert"]["id"]

    deadline = time.time() + 3
    while time.time() < deadline:
        response = client.get(f"/api/v1/transactions/{transaction_id}")
        if response.status_code == 200:
            break
        time.sleep(0.1)
    assert response.status_code == 200
    assert response.json()["transaction"]["id"] == transaction_id

    alert = client.get(f"/api/v1/alerts/{alert_id}")
    assert alert.status_code == 200
    payload = alert.json()
    assert payload["transaction"]["id"] == transaction_id
    assert payload["events"]

    patched = client.patch(
        f"/api/v1/alerts/{alert_id}",
        json={"status": "resolved", "assignee": "test.analyst", "note": "Cardholder confirmed."},
        headers={"X-Operator": "test.analyst"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "resolved"
    assert patched.json()["resolved_at"]

    audit = client.get("/api/v1/audit", params={"entity_type": "alert", "entity_id": alert_id}).json()
    assert any(event["action"] == "alert.updated" for event in audit["data"])


def test_overview_and_analytics_aggregate(client):
    overview = client.get("/api/v1/overview", params={"window": "24h"})
    assert overview.status_code == 200
    body = overview.json()
    assert body["kpis"]["transactions"]["value"] >= 1
    assert len(body["series"]) >= 10
    assert "label_metrics" in body

    analytics = client.get("/api/v1/analytics", params={"window": "7d"})
    assert analytics.status_code == 200
    assert len(analytics.json()["risk_histogram"]) == 10


def test_transaction_search(client):
    response = client.get("/api/v1/transactions", params={"page_size": 10, "decision": "block"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] >= 1
    assert all(row["decision"] == "block" for row in body["data"])


def test_settings_validation(client):
    bad = client.patch("/api/v1/settings", json={"review_threshold": 90, "block_threshold": 80})
    assert bad.status_code == 422

    good = client.patch("/api/v1/settings", json={"review_threshold": 35})
    assert good.status_code == 200
    assert good.json()["review_threshold"] == 35


def test_system_endpoint(client):
    response = client.get("/api/v1/system")
    assert response.status_code == 200
    body = response.json()
    assert body["pipeline"]["model_version"]
    assert body["storage"]["engine"] == "sqlite"
    assert runtime.pipeline is not None
