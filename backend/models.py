"""Persistent schema.

The write model mirrors a payment-risk platform: immutable scored transactions,
an alert/review queue, an audit trail and versioned engine configuration. Labels
are nullable because they only exist after a chargeback decision; the synthetic
data generator fills them so the demo can report measured precision/recall.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_id: Mapped[str] = mapped_column(String(48), index=True)
    card_id: Mapped[str | None] = mapped_column(String(48), index=True, nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="IDR")

    merchant_id: Mapped[str] = mapped_column(String(48))
    merchant_name: Mapped[str] = mapped_column(String(120))
    merchant_category: Mapped[str] = mapped_column(String(48), index=True)
    merchant_country: Mapped[str] = mapped_column(String(2), index=True)

    channel: Mapped[str] = mapped_column(String(16), index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    email_domain: Mapped[str | None] = mapped_column(String(64), nullable=True)

    risk_score: Mapped[int] = mapped_column(Integer, index=True)
    model_score: Mapped[float] = mapped_column(Float)
    rule_score: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(12), index=True)
    reason_codes: Mapped[str] = mapped_column(Text, default="[]")
    features: Mapped[str] = mapped_column(Text, default="{}")
    model_version: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[float] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime)

    __table_args__ = (
        Index("ix_transactions_created_decision", "created_at", "decision"),
        Index("ix_transactions_created_risk", "created_at", "risk_score"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(48), index=True, unique=True)
    severity: Mapped[str] = mapped_column(String(12), index=True)
    risk_score: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    assignee: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("ix_alerts_status_created", "status", "created_at"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class EngineSetting(Base):
    __tablename__ = "engine_settings"

    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(48), unique=True)
    algorithm: Mapped[str] = mapped_column(String(64))
    trained_at: Mapped[datetime] = mapped_column(DateTime)
    training_rows: Mapped[int] = mapped_column(Integer)
    metrics_json: Mapped[str] = mapped_column(Text)
    features_json: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
