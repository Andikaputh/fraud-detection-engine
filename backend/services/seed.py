"""Demo data seeding.

A cold start with an empty database looks broken, so a fresh install is seeded
with seven days of labelled history. Seeding runs through the real scoring
pipeline, not a shortcut: every row is produced by the same features and model the
live stream uses. This is what makes the dashboard's precision numbers honest.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import func

from backend.core.logging import get_logger
from backend.core.timeutil import utcnow
from backend.database import session_scope
from backend.models import Alert, AuditEvent, ModelVersion, Transaction
from backend.services.writer import TransactionWriter
from backend.stream.pipeline import TransactionPipeline
from backend.stream.world import ANALYSTS, World

logger = get_logger("sentinel.seed")

# Seven days at a uniform average rate keeps every analytics window on the same
# scale. A dense 48-hour block followed by a sparse tail produced a visible cliff
# in the 7-day chart and model drift, which looked like an outage rather than a
# deliberate retention boundary.
HISTORY_DAYS = 7
HISTORY_ROWS = 92_400
SEED_CHUNK_SIZE = 6_000


def is_seeded() -> bool:
    with session_scope() as session:
        count = session.query(func.count(Transaction.id)).scalar() or 0
    return count > 0


def wipe_all() -> None:
    with session_scope() as session:
        session.query(Alert).delete()
        session.query(AuditEvent).delete()
        session.query(Transaction).delete()
        session.query(ModelVersion).delete()


def sync_model_version(card: dict) -> None:
    with session_scope() as session:
        session.query(ModelVersion).update({ModelVersion.is_active: False})
        existing = session.query(ModelVersion).filter_by(version=card["version"]).first()
        if existing:
            existing.is_active = True
            existing.metrics_json = json.dumps(card["metrics"])
            existing.features_json = json.dumps(card["feature_names"])
        else:
            session.add(
                ModelVersion(
                    version=card["version"],
                    algorithm=card["algorithm"],
                    trained_at=utcnow(),
                    training_rows=card["training_rows"],
                    metrics_json=json.dumps(card["metrics"]),
                    features_json=json.dumps(card["feature_names"]),
                    is_active=True,
                )
            )


def warm_state(pipeline: TransactionPipeline, limit: int = 800) -> None:
    """Rebuild velocity / customer state from the persisted tail after a restart."""
    with session_scope() as session:
        rows = (
            session.query(Transaction)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        events = []
        for row in rows:
            events.append(
                {
                    "transaction_id": row.id,
                    "customer_id": row.customer_id,
                    "card_id": row.card_id,
                    "amount": row.amount,
                    "merchant": {
                        "id": row.merchant_id,
                        "name": row.merchant_name,
                        "category": row.merchant_category,
                        "country": row.merchant_country,
                    },
                    "channel": row.channel,
                    "device_id": row.device_id,
                    "ip_country": row.ip_country,
                    "created_at": row.created_at,
                    "context": {},
                }
            )
    pipeline.store.warm(events)
    logger.info("warmed feature state from %d transactions", len(events))


def _assign_review_state(alert: dict, rng: random.Random) -> dict:
    age_hours = max((utcnow() - alert["created_at"]).total_seconds() / 3600, 0.1)
    max_offset_minutes = max(int(age_hours * 60) - 1, 1)

    def after_created(low: int, high: int) -> "datetime":
        return alert["created_at"] + timedelta(
            minutes=min(rng.randint(low, high), max_offset_minutes)
        )

    roll = rng.random()
    if age_hours > 72:
        status = (
            "resolved"
            if roll < 0.72
            else "false_positive"
            if roll < 0.88
            else "investigating"
            if roll < 0.96
            else "open"
        )
    elif age_hours > 24:
        status = (
            "resolved"
            if roll < 0.52
            else "false_positive"
            if roll < 0.70
            else "investigating"
            if roll < 0.86
            else "open"
        )
    else:
        status = (
            "open"
            if roll < 0.24
            else "investigating"
            if roll < 0.42
            else "resolved"
            if roll < 0.84
            else "false_positive"
        )

    alert["status"] = status
    if status != "open":
        alert["assignee"] = rng.choice(ANALYSTS)
    if status == "resolved":
        alert["resolved_at"] = after_created(20, 420)
        alert["note"] = rng.choice(
            [
                "Confirmed with the cardholder. Card reissued and device removed.",
                "Matched a known card-testing cluster. Merchant notified.",
                "Customer verified the purchase after step-up authentication.",
            ]
        )
        alert["updated_at"] = alert["resolved_at"]
    elif status == "false_positive":
        alert["resolved_at"] = after_created(10, 240)
        alert["note"] = "Legitimate high-value purchase confirmed by the customer."
        alert["updated_at"] = alert["resolved_at"]
    elif status == "investigating":
        alert["updated_at"] = after_created(2, 90)
    return alert


def _audit_rows(alerts: list[dict], rng: random.Random) -> list[AuditEvent]:
    rows: list[AuditEvent] = []
    for alert in alerts:
        rows.append(
            AuditEvent(
                actor="system",
                action="alert.created",
                entity_type="alert",
                entity_id=alert["id"],
                metadata_json=json.dumps({"risk_score": alert["risk_score"], "severity": alert["severity"]}),
                created_at=alert["created_at"],
            )
        )
        if alert.get("assignee"):
            rows.append(
                AuditEvent(
                    actor="system",
                    action="alert.assigned",
                    entity_type="alert",
                    entity_id=alert["id"],
                    metadata_json=json.dumps({"assignee": alert["assignee"]}),
                    created_at=alert["created_at"] + timedelta(minutes=rng.randint(1, 30)),
                )
            )
        if alert.get("resolved_at"):
            rows.append(
                AuditEvent(
                    actor=alert.get("assignee") or "system",
                    action="alert.resolved",
                    entity_type="alert",
                    entity_id=alert["id"],
                    metadata_json=json.dumps({"status": alert["status"]}),
                    created_at=alert["resolved_at"],
                )
            )
    return rows


def seed_demo(
    pipeline: TransactionPipeline,
    writer: TransactionWriter,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    rng = random.Random(1042)
    world = World(seed=42)
    events = world.history(HISTORY_ROWS, days=HISTORY_DAYS)
    events.sort(key=lambda item: item["timestamp"])

    alerts: list[dict] = []
    total_rows = 0
    for offset in range(0, len(events), SEED_CHUNK_SIZE):
        chunk = events[offset : offset + SEED_CHUNK_SIZE]
        rows, scored_alerts = pipeline.score_events(chunk)
        for alert in scored_alerts:
            alerts.append(_assign_review_state(alert, rng))
        writer.enqueue_bulk(rows, scored_alerts)

        total_rows += len(rows)
        pipeline.counters["total"] += len(rows)
        for row in rows:
            pipeline.counters[row["decision"]] += 1
            if row["label"] == "fraud":
                pipeline.counters["fraud_label"] += 1
        if on_progress:
            on_progress(offset + len(chunk), len(events))
        # Keep RSS bounded on small hosts. Batch inference is faster than the
        # SQLite writer, so an unthrottled producer would hold the whole seed in
        # the queue before the first commit lands.
        if writer.queue.qsize() >= 4:
            writer.queue.join()

    del events
    writer.queue.join()

    audits = _audit_rows(alerts, rng)
    with session_scope() as session:
        if audits:
            session.add_all(audits)
        session.add(
            AuditEvent(
                actor="system",
                action="engine.seeded",
                entity_type="environment",
                entity_id="demo",
                metadata_json=json.dumps(
                    {
                        "transactions": total_rows,
                        "alerts": len(alerts),
                        "days": HISTORY_DAYS,
                    }
                ),
                created_at=utcnow(),
            )
        )
    sync_model_version(pipeline.scorer.card)

    logger.info(
        "seeded %d transactions and %d alerts over %d days",
        total_rows,
        len(alerts),
        HISTORY_DAYS,
    )
    return {"transactions": total_rows, "alerts": len(alerts), "days": HISTORY_DAYS}


def reset_demo(
    pipeline: TransactionPipeline,
    writer: TransactionWriter,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    with session_scope() as session:
        session.query(Alert).delete()
        session.query(AuditEvent).delete()
        session.query(Transaction).delete()
    pipeline.reset_state()
    return seed_demo(pipeline, writer, on_progress=on_progress)
