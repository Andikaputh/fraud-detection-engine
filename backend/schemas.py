"""Request/response contracts.

Pydantic models are the public API boundary. The inbound transaction schema is
intentionally close to ISO 20022 / card-authorisation fields so the simulator and
a real payment gateway can share the same endpoint.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MerchantIn(BaseModel):
    id: str = Field(default="mrc_unknown", max_length=48)
    name: str = Field(default="Unknown merchant", max_length=120)
    category: str = Field(default="general", max_length=48)
    country: str = Field(default="ID", min_length=2, max_length=2)
    risk_tier: float = Field(default=0.15, ge=0, le=1)


class ContextIn(BaseModel):
    home_country: str | None = Field(default=None, max_length=2)
    account_age_days: int | None = Field(default=None, ge=0)
    chargebacks: int | None = Field(default=None, ge=0)
    avg_amount: float | None = Field(default=None, gt=0)


class TransactionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    transaction_id: str | None = Field(default=None, max_length=48)
    external_id: str | None = Field(default=None, max_length=64)
    customer_id: str = Field(min_length=1, max_length=48)
    card_id: str | None = Field(default=None, max_length=48)
    amount: float = Field(gt=0, le=1_000_000_000_000)
    currency: str = Field(default="IDR", min_length=3, max_length=3)
    merchant: MerchantIn = Field(default_factory=MerchantIn)
    channel: Literal["ecommerce", "pos", "atm", "transfer", "subscription"] = "ecommerce"
    device_id: str | None = Field(default=None, max_length=64)
    ip_country: str | None = Field(default=None, max_length=2)
    email: str | None = Field(default=None, max_length=160)
    timestamp: datetime | None = None
    context: ContextIn | None = None

    @field_validator("ip_country", "currency")
    @classmethod
    def uppercase(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str | None
    customer_id: str
    card_id: str | None
    amount: float
    currency: str
    merchant_id: str
    merchant_name: str
    merchant_category: str
    merchant_country: str
    channel: str
    device_id: str | None
    ip_country: str | None
    email_domain: str | None
    risk_score: int
    model_score: float
    rule_score: float
    decision: str
    reasons: list[dict] = Field(default_factory=list)
    features: dict = Field(default_factory=dict)
    model_version: str
    latency_ms: float
    label: str | None
    created_at: str
    scored_at: str


class AlertOut(BaseModel):
    id: str
    transaction_id: str
    severity: str
    risk_score: int
    status: str
    assignee: str | None
    note: str | None
    created_at: str
    updated_at: str
    resolved_at: str | None
    transaction: TransactionOut | None = None


class AlertUpdate(BaseModel):
    status: Literal["open", "investigating", "resolved", "false_positive"] | None = None
    assignee: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=4000)


class SettingsPatch(BaseModel):
    review_threshold: int | None = Field(default=None, ge=1, le=99)
    block_threshold: int | None = Field(default=None, ge=2, le=100)
    amount_sensitivity: float | None = Field(default=None, ge=100_000, le=1_000_000_000)
    velocity_limit_1m: int | None = Field(default=None, ge=2, le=50)
    velocity_limit_10m: int | None = Field(default=None, ge=3, le=200)
    auto_block: bool | None = None
    telegram_enabled: bool | None = None
    simulator_tps: float | None = Field(default=None, ge=0.2, le=50)


class WhatIfRequest(BaseModel):
    amount: float = Field(gt=0, le=1_000_000_000_000)
    customer_id: str = "cus_whatif"
    merchant_category: str = "electronics"
    merchant_country: str = "ID"
    channel: Literal["ecommerce", "pos", "atm", "transfer", "subscription"] = "ecommerce"
    ip_country: str = "ID"
    device_id: str | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    new_customer: bool = True


class BurstRequest(BaseModel):
    count: int = Field(default=12, ge=1, le=200)
    pattern: Literal["card_testing", "account_takeover", "stolen_card", "mixed"] = "mixed"


class DecisionSeriesPoint(BaseModel):
    t: str
    total: int
    blocked: int
    review: int
    fraud: int


class OverviewOut(BaseModel):
    window: str
    generated_at: str
    kpis: dict
    series: list[dict]
    risk_distribution: list[dict]
    decisions: dict
    top_reasons: list[dict]
    top_merchants: list[dict]
    channels: list[dict]
    system: dict


class PageMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int


class TransactionPage(BaseModel):
    data: list[TransactionOut]
    meta: PageMeta


class AlertPage(BaseModel):
    data: list[AlertOut]
    meta: PageMeta


class StreamEvent(BaseModel):
    type: str
    data: dict
    at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
