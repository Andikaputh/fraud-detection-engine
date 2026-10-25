"""Operational, model and streaming endpoints."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.api.deps import get_pipeline, operator_identity, require_write_access
from backend.api.runtime import runtime
from backend.config import settings
from backend.core.logging import get_logger
from backend.core.settings_store import get_engine_config, public_settings, update_settings
from backend.core.timeutil import to_iso, utcnow
from backend.database import SessionLocal, session_scope
from backend.ml.features import HIGH_RISK_CATEGORIES, FeatureStore
from backend.models import Alert, AuditEvent, ModelVersion, Transaction
from backend.schemas import BurstRequest, SettingsPatch, WhatIfRequest
from backend.services import analytics, audit, backfill
from backend.services.serialization import loads, transaction_to_dict
from backend.stream.broadcaster import format_sse
from backend.stream.world import World

router = APIRouter()
logger = get_logger("sentinel.api")


@router.get("/health")
def health() -> dict[str, Any]:
    db_status = "ok"
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {exc}"

    pipeline = runtime.pipeline
    model_version = pipeline.scorer.card.get("version") if pipeline else None
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": settings.service_name,
        "version": settings.version,
        "commit": os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or None,
        "environment": settings.environment,
        "database": db_status,
        "model_version": model_version,
        "ingest_mode": settings.ingest_mode,
        "seeding": runtime.seeding,
        "uptime_seconds": int(time.time() - runtime.started_at) if runtime.started_at else 0,
        "timestamp": to_iso(utcnow()),
    }


@router.get("/ready")
def ready() -> dict[str, Any]:
    if runtime.pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline not ready")
    return {"ready": True}


@router.get("/system")
def system_status() -> dict[str, Any]:
    pipeline = get_pipeline()
    database_size = None
    if settings.is_sqlite:
        path = Path(settings.database_url.replace("sqlite:///", ""))
        database_size = path.stat().st_size if path.exists() else 0

    ingest: dict[str, Any]
    if runtime.kafka:
        ingest = runtime.kafka.status()
    elif runtime.simulator:
        ingest = {
            "mode": "simulator",
            "running": True,
            "emitted": runtime.simulator.emitted,
            "tps": runtime.simulator.tps,
        }
    else:
        ingest = {"mode": settings.ingest_mode, "running": False}

    from backend.services.alerting import dispatcher

    return {
        "service": {
            "name": settings.app_name,
            "version": settings.version,
            "environment": settings.environment,
            "demo_mode": settings.demo_mode,
        },
        "pipeline": pipeline.system_status(),
        "ingest": ingest,
        "alerts": analytics.alert_stats(),
        "delivery": dispatcher.stats(),
        "storage": {
            "engine": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
            "size_bytes": database_size,
            "retention_days": settings.retention_days,
        },
        "config": public_settings(),
        "backfill": runtime.backfill_status(),
        "server_time": to_iso(utcnow()),
    }


@router.get("/backfill")
def backfill_status() -> dict[str, Any]:
    return backfill.snapshot()


@router.get("/settings")
def read_settings() -> dict[str, Any]:
    return public_settings()


@router.patch("/settings")
def patch_settings(
    body: SettingsPatch,
    request: Request,
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    current = get_engine_config()
    candidate = {**current, **body.model_dump(exclude_none=True)}
    if int(candidate["review_threshold"]) >= int(candidate["block_threshold"]):
        raise HTTPException(status_code=422, detail="review_threshold must be lower than block_threshold")

    updated = update_settings(body.model_dump(exclude_none=True), actor=operator_identity(request))
    audit.record(
        "settings.updated",
        "environment",
        settings.environment,
        actor=operator_identity(request),
        metadata={key: body.model_dump(exclude_none=True)[key] for key in body.model_dump(exclude_none=True)},
    )
    analytics.invalidate_cache()
    runtime.pipeline.bus.publish("settings.updated", public_settings())
    return public_settings()


@router.get("/model")
def model_info() -> dict[str, Any]:
    pipeline = get_pipeline()
    card = pipeline.scorer.card
    with session_scope() as session:
        versions = session.query(ModelVersion).order_by(ModelVersion.trained_at.desc()).limit(10).all()
        version_rows = [
            {
                "version": row.version,
                "algorithm": row.algorithm,
                "trained_at": to_iso(row.trained_at),
                "training_rows": row.training_rows,
                "is_active": row.is_active,
                "metrics": loads(row.metrics_json, {}),
            }
            for row in versions
        ]
    artifact = settings.model_dir / "model.joblib"
    return {
        "card": card,
        "artifact": {
            "path": "artifacts/model.joblib",
            "size_bytes": artifact.stat().st_size if artifact.exists() else 0,
            "loaded_at": to_iso(utcnow()),
        },
        "versions": version_rows,
        "live": pipeline.system_status(),
    }


@router.post("/model/score")
def what_if(body: WhatIfRequest) -> dict[str, Any]:
    pipeline = get_pipeline()
    hour = body.hour if body.hour is not None else 14
    timestamp = utcnow().replace(hour=hour, minute=0, second=0, microsecond=0)
    payload = {
        "customer_id": body.customer_id,
        "card_id": f"card_{body.customer_id[-4:]}",
        "amount": body.amount,
        "merchant": {
            "id": "mrc_whatif",
            "name": "What-if merchant",
            "category": body.merchant_category,
            "country": body.merchant_country.upper(),
            "risk_tier": HIGH_RISK_CATEGORIES.get(body.merchant_category, 0.15),
        },
        "channel": body.channel,
        "device_id": "dev_whatif_new" if body.new_customer else None,
        "ip_country": body.ip_country.upper(),
        "timestamp": timestamp,
        "context": {
            "home_country": "ID",
            "account_age_days": 1 if body.new_customer else 420,
            "chargebacks": 0,
            "avg_amount": 250_000,
        },
    }
    event = pipeline.normalize(payload)
    store = FeatureStore()
    features, meta = store.build(event)
    assessment = pipeline.scorer.assess(event, features, meta, get_engine_config())
    return {
        "risk_score": assessment["risk_score"],
        "decision": assessment["decision"],
        "model_score": assessment["model_score"],
        "rule_score": assessment["rule_score"],
        "severity": assessment["severity"],
        "reasons": assessment["reasons"],
        "features": {key: round(value, 3) for key, value in features.items()},
        "context": meta,
    }


@router.post("/simulate/burst")
def simulate_burst(
    body: BurstRequest,
    request: Request,
    _: None = Depends(require_write_access),
) -> dict[str, Any]:
    pipeline = get_pipeline()
    started = time.perf_counter()
    if runtime.simulator:
        emitted = runtime.simulator.burst(body.pattern, body.count)
    else:
        world = World(seed=None)
        events = world.burst(body.pattern, body.count, utcnow())
        for payload in events:
            pipeline.process(payload)
        emitted = len(events)
    analytics.invalidate_cache()
    audit.record(
        "simulation.burst",
        "environment",
        settings.environment,
        actor=operator_identity(request),
        metadata={"pattern": body.pattern, "count": emitted},
    )
    return {
        "accepted": emitted,
        "pattern": body.pattern,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@router.post("/demo/reset")
def demo_reset(request: Request, _: None = Depends(require_write_access)) -> dict[str, Any]:
    if not settings.demo_mode:
        raise HTTPException(status_code=403, detail="Reset is disabled outside demo mode")
    get_pipeline()
    actor = operator_identity(request)
    if not backfill.start(reset=True, actor=actor):
        raise HTTPException(status_code=409, detail="A reset or backfill is already running")
    audit.record(
        "demo.reset.requested",
        "environment",
        settings.environment,
        actor=actor,
        metadata={"mode": "background"},
    )
    return {"status": "seeding", "transactions": 0, "alerts": 0}


@router.get("/audit")
def audit_log(
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    with session_scope() as session:
        query = session.query(AuditEvent)
        if entity_type:
            query = query.filter(AuditEvent.entity_type == entity_type)
        if entity_id:
            query = query.filter(AuditEvent.entity_id == entity_id)
        if action:
            query = query.filter(AuditEvent.action == action)
        rows = query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).all()
        data = [
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "metadata": loads(row.metadata_json, {}),
                "created_at": to_iso(row.created_at),
            }
            for row in rows
        ]
    return {"data": data}


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    pipeline = get_pipeline()
    queue = pipeline.bus.subscribe()

    async def event_generator():
        try:
            yield "retry: 3000\n\n"
            yield format_sse(
                {
                    "type": "ready",
                    "sequence": 0,
                    "data": {
                        "server_time": to_iso(utcnow()),
                        "model_version": pipeline.scorer.card.get("version"),
                        "ingest_mode": settings.ingest_mode,
                    },
                }
            )
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield format_sse(payload)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            pipeline.bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
