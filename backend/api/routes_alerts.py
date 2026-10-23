"""Alert / review-queue endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_

from backend.api.deps import get_pipeline, operator_identity, require_write_access
from backend.core.timeutil import parse_window, to_iso, utcnow
from backend.core.settings_store import get_engine_config
from backend.database import session_scope
from backend.models import Alert, AuditEvent, Transaction
from backend.schemas import AlertPage, AlertUpdate
from backend.services import analytics, audit
from backend.services.serialization import alert_to_dict, loads, transaction_to_dict

router = APIRouter()

VALID_STATUS = {"open", "investigating", "resolved", "false_positive"}


@router.get("/alerts/stats")
def get_alert_stats() -> dict[str, Any]:
    return analytics.alert_stats()


@router.get("/alerts", response_model=AlertPage)
def list_alerts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None, pattern="^(critical|high|medium)$"),
    window: str | None = Query(default=None, pattern="^(1h|6h|24h|7d|30d)$"),
    min_risk: int | None = Query(default=None, ge=0, le=100),
    search: str | None = Query(default=None, max_length=120),
    sort_by: str = Query(default="created_at", pattern="^(created_at|risk_score)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    statuses = [item for item in (status or "").split(",") if item in VALID_STATUS]
    with session_scope() as session:
        query = session.query(Alert, Transaction).join(Transaction, Alert.transaction_id == Transaction.id)
        if statuses:
            query = query.filter(Alert.status.in_(statuses))
        if severity:
            query = query.filter(Alert.severity == severity)
        if window:
            query = query.filter(Alert.created_at >= utcnow() - parse_window(window))
        if min_risk is not None:
            query = query.filter(Alert.risk_score >= min_risk)
        if search:
            needle = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Alert.id.ilike(needle),
                    Alert.transaction_id.ilike(needle),
                    Transaction.customer_id.ilike(needle),
                    Transaction.merchant_name.ilike(needle),
                )
            )

        total = query.count()
        column = Alert.created_at if sort_by == "created_at" else Alert.risk_score
        ordering = column.desc() if sort_dir == "desc" else column.asc()
        rows = (
            query.order_by(ordering, Alert.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        data = [alert_to_dict(alert, transaction_to_dict(transaction)) for alert, transaction in rows]

    pages = max((total + page_size - 1) // page_size, 1)
    return {
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size, "pages": pages},
    }


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str) -> dict[str, Any]:
    with session_scope() as session:
        row = session.query(Alert, Transaction).join(Transaction, Alert.transaction_id == Transaction.id).filter(Alert.id == alert_id).first()
        if row:
            alert, transaction = row
            events = (
                session.query(AuditEvent)
                .filter(AuditEvent.entity_type == "alert", AuditEvent.entity_id == alert_id)
                .order_by(AuditEvent.created_at.asc())
                .all()
            )
            event_rows = [
                {
                    "id": event.id,
                    "actor": event.actor,
                    "action": event.action,
                    "metadata": loads(event.metadata_json, {}),
                    "created_at": to_iso(event.created_at),
                }
                for event in events
            ]
            if not any(event["action"] == "alert.created" for event in event_rows):
                event_rows.insert(
                    0,
                    {
                        "id": 0,
                        "actor": "system",
                        "action": "alert.created",
                        "metadata": {"risk_score": alert.risk_score, "severity": alert.severity},
                        "created_at": to_iso(alert.created_at),
                    },
                )

            payload = alert_to_dict(alert, transaction_to_dict(transaction))
            payload["events"] = event_rows
            payload["policy"] = {
                "review_threshold": get_engine_config()["review_threshold"],
                "block_threshold": get_engine_config()["block_threshold"],
            }
            return payload

    # Read-after-write: the alert may still be in the write queue. Serve the
    # in-memory copy rather than returning a misleading 404.
    pipeline = get_pipeline()
    cached_alert = pipeline.cached_alert(alert_id)
    if cached_alert:
        transaction = pipeline.cached_transaction(cached_alert["transaction_id"])
        payload = alert_to_dict(cached_alert, transaction_to_dict(transaction) if transaction else None)
        payload["events"] = [
            {
                "id": 0,
                "actor": "system",
                "action": "alert.created",
                "metadata": {"risk_score": cached_alert["risk_score"], "severity": cached_alert["severity"]},
                "created_at": to_iso(cached_alert["created_at"]),
            }
        ]
        payload["policy"] = {
            "review_threshold": get_engine_config()["review_threshold"],
            "block_threshold": get_engine_config()["block_threshold"],
        }
        return payload

    raise HTTPException(status_code=404, detail="Alert not found")


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: str,
    body: AlertUpdate,
    request: Request,
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=422, detail="No fields to update")

    with session_scope() as session:
        alert = session.get(Alert, alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        previous_status = alert.status
        now = utcnow()
        if "status" in payload:
            alert.status = payload["status"]
            if payload["status"] in {"resolved", "false_positive"}:
                alert.resolved_at = now
            else:
                alert.resolved_at = None
        if "assignee" in payload:
            alert.assignee = payload["assignee"] or None
        if "note" in payload:
            alert.note = payload["note"]
        alert.updated_at = now
        session.flush()

        transaction = session.get(Transaction, alert.transaction_id)
        response = alert_to_dict(alert, transaction_to_dict(transaction) if transaction else None)
        session.expunge(alert)

    actor = operator_identity(request)
    audit.record(
        "alert.updated",
        "alert",
        alert_id,
        actor=actor,
        metadata={
            "from": previous_status,
            "to": payload.get("status", previous_status),
            "assignee": payload.get("assignee"),
            "note": payload.get("note"),
        },
    )
    analytics.invalidate_cache()
    get_pipeline().bus.publish("alert.updated", response)
    return response
