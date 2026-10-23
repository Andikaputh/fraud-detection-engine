"""Transaction search, detail and ingestion endpoints."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_

from backend.api.deps import get_pipeline, operator_identity, require_write_access
from backend.core.timeutil import parse_window, to_iso, utcnow
from backend.database import session_scope
from backend.models import Alert, Transaction
from backend.schemas import TransactionIn, TransactionPage
from backend.services import analytics, audit
from backend.services.serialization import alert_to_dict, transaction_to_dict

router = APIRouter()


@router.get("/transactions", response_model=TransactionPage)
def list_transactions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    window: str | None = Query(default=None, pattern="^(1h|6h|24h|7d|30d)$"),
    decision: str | None = Query(default=None, pattern="^(allow|review|block)$"),
    label: str | None = Query(default=None, pattern="^(fraud|legit)$"),
    min_risk: int | None = Query(default=None, ge=0, le=100),
    max_risk: int | None = Query(default=None, ge=0, le=100),
    customer_id: str | None = None,
    merchant_category: str | None = None,
    country: str | None = Query(default=None, max_length=2),
    channel: str | None = None,
    search: str | None = Query(default=None, max_length=120),
    sort_by: str = Query(default="created_at", pattern="^(created_at|risk_score|amount)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> dict[str, Any]:
    with session_scope() as session:
        query = session.query(Transaction)
        if window:
            query = query.filter(Transaction.created_at >= utcnow() - parse_window(window))
        if decision:
            query = query.filter(Transaction.decision == decision)
        if label:
            query = query.filter(Transaction.label == label)
        if min_risk is not None:
            query = query.filter(Transaction.risk_score >= min_risk)
        if max_risk is not None:
            query = query.filter(Transaction.risk_score <= max_risk)
        if customer_id:
            query = query.filter(Transaction.customer_id == customer_id)
        if merchant_category:
            query = query.filter(Transaction.merchant_category == merchant_category)
        if country:
            query = query.filter(Transaction.merchant_country == country.upper())
        if channel:
            query = query.filter(Transaction.channel == channel)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Transaction.id.ilike(pattern),
                    Transaction.external_id.ilike(pattern),
                    Transaction.customer_id.ilike(pattern),
                    Transaction.merchant_name.ilike(pattern),
                )
            )

        total = query.count()
        column = getattr(Transaction, sort_by)
        ordering = column.desc() if sort_dir == "desc" else column.asc()
        rows = (
            query.order_by(ordering, Transaction.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        data = [transaction_to_dict(row) for row in rows]

    pages = max((total + page_size - 1) // page_size, 1)
    return {
        "data": data,
        "meta": {"total": total, "page": page, "page_size": page_size, "pages": pages},
    }


@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str) -> dict[str, Any]:
    pipeline = get_pipeline()
    with session_scope() as session:
        row = session.get(Transaction, transaction_id)
        if row:
            transaction = transaction_to_dict(row)
            alert = session.query(Alert).filter(Alert.transaction_id == transaction_id).first()
            return {
                "transaction": transaction,
                "alert": alert_to_dict(alert, transaction) if alert else None,
            }

    cached = pipeline.cached_transaction(transaction_id)
    if cached:
        return {"transaction": transaction_to_dict(cached), "alert": None}
    raise HTTPException(status_code=404, detail="Transaction not found")


@router.post("/transactions")
def ingest_transaction(
    body: TransactionIn,
    request: Request,
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    pipeline = get_pipeline()
    payload = body.model_dump(mode="python")
    row, alert = pipeline.process(payload, persist_sync=True)
    analytics.invalidate_cache()
    audit.record(
        "transaction.ingested",
        "transaction",
        row["id"],
        actor=operator_identity(request),
        metadata={"amount": row["amount"], "decision": row["decision"], "risk_score": row["risk_score"]},
    )
    return {
        "transaction": transaction_to_dict(row),
        "alert": alert_to_dict(alert) if alert else None,
        "processed_at": to_iso(utcnow()),
    }
