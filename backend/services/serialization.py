"""Row <-> API serialisation helpers."""

from __future__ import annotations

import json
from typing import Any

from backend.core.timeutil import to_iso


def loads(raw: str | None, default: Any = None) -> Any:
    if not raw:
        return default if default is not None else []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default if default is not None else []


def transaction_to_dict(row: Any) -> dict:
    get = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
    created_at = get("created_at")
    scored_at = get("scored_at")
    return {
        "id": get("id"),
        "external_id": get("external_id"),
        "customer_id": get("customer_id"),
        "card_id": get("card_id"),
        "amount": get("amount"),
        "currency": get("currency", "IDR"),
        "merchant_id": get("merchant_id"),
        "merchant_name": get("merchant_name"),
        "merchant_category": get("merchant_category"),
        "merchant_country": get("merchant_country"),
        "channel": get("channel"),
        "device_id": get("device_id"),
        "ip_country": get("ip_country"),
        "email_domain": get("email_domain"),
        "risk_score": get("risk_score"),
        "model_score": get("model_score"),
        "rule_score": get("rule_score"),
        "decision": get("decision"),
        "reasons": loads(get("reason_codes") or get("reasons"), []),
        "features": loads(get("features"), {}),
        "model_version": get("model_version"),
        "latency_ms": round(float(get("latency_ms") or 0), 2),
        "label": get("label"),
        "created_at": to_iso(created_at) if created_at else None,
        "scored_at": to_iso(scored_at) if scored_at else None,
    }


def alert_to_dict(row: Any, transaction: dict | None = None) -> dict:
    get = row.get if isinstance(row, dict) else lambda key, default=None: getattr(row, key, default)
    created_at = get("created_at")
    updated_at = get("updated_at")
    resolved_at = get("resolved_at")
    return {
        "id": get("id"),
        "transaction_id": get("transaction_id"),
        "severity": get("severity"),
        "risk_score": get("risk_score"),
        "status": get("status"),
        "assignee": get("assignee"),
        "note": get("note"),
        "created_at": to_iso(created_at) if created_at else None,
        "updated_at": to_iso(updated_at) if updated_at else None,
        "resolved_at": to_iso(resolved_at) if resolved_at else None,
        "transaction": transaction,
    }


def live_summary(row: dict) -> dict:
    """Compact payload for the SSE feed."""
    return {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "amount": row["amount"],
        "currency": row.get("currency", "IDR"),
        "merchant_name": row["merchant_name"],
        "merchant_category": row["merchant_category"],
        "merchant_country": row["merchant_country"],
        "channel": row["channel"],
        "risk_score": row["risk_score"],
        "model_score": row["model_score"],
        "decision": row["decision"],
        "reasons": loads(row.get("reason_codes"), []),
        "created_at": to_iso(row["created_at"]),
        "latency_ms": round(float(row.get("latency_ms", 0)), 2),
        "label": row.get("label"),
    }
