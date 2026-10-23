"""Scoring pipeline shared by the API, the simulator and the Kafka consumer.

One event enters, one immutable decision record plus (optionally) one alert leaves.
The hot path contains no network calls and no disk writes.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any

from backend.config import settings
from backend.core.logging import get_logger
from backend.core.settings_store import get_engine_config
from backend.core.timeutil import to_iso, utcnow
from backend.ml.features import FeatureStore
from backend.ml.scorer import get_scorer
from backend.services.alerting import dispatcher
from backend.services.serialization import live_summary
from backend.services.writer import TransactionWriter
from backend.stream.broadcaster import EventBus

logger = get_logger("sentinel.pipeline")


class TransactionPipeline:
    def __init__(self, bus: EventBus, writer: TransactionWriter) -> None:
        self.bus = bus
        self.writer = writer
        self.store = FeatureStore()
        self.scorer = get_scorer()
        self.started_at = time.time()

        self._lock = threading.Lock()
        self._txn_cache: OrderedDict[str, dict] = OrderedDict()
        self._alert_cache: OrderedDict[str, dict] = OrderedDict()
        self.counters = {"total": 0, "allow": 0, "review": 0, "block": 0, "fraud_label": 0}
        self._latencies: deque[float] = deque(maxlen=1000)
        self.last_event_at: str | None = None

    # ----------------------------------------------------------- normalisation
    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        merchant = payload.get("merchant") or {}
        if isinstance(merchant, str):
            merchant = {}
        timestamp = payload.get("timestamp") or utcnow()
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = utcnow()
        if getattr(timestamp, "tzinfo", None) is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        if timestamp > utcnow():
            timestamp = utcnow()

        email = payload.get("email") or ""
        email_domain = payload.get("email_domain") or (email.split("@")[-1] if "@" in email else None)

        event = {
            "id": payload.get("transaction_id") or payload.get("id") or f"txn_{uuid.uuid4().hex[:16]}",
            "external_id": payload.get("external_id"),
            "customer_id": str(payload.get("customer_id") or "cus_unknown"),
            "card_id": payload.get("card_id"),
            "amount": round(float(payload.get("amount") or 0), 2),
            "currency": (payload.get("currency") or "IDR").upper(),
            "merchant_id": merchant.get("id") or payload.get("merchant_id") or "mrc_unknown",
            "merchant_name": merchant.get("name") or payload.get("merchant_name") or "Unknown merchant",
            "merchant_category": merchant.get("category") or payload.get("merchant_category") or "general",
            "merchant_country": (merchant.get("country") or payload.get("merchant_country") or "ID").upper(),
            "merchant_risk": float(
                merchant.get("risk_tier", payload.get("merchant_risk", 0.15)) or 0.15
            ),
            "channel": payload.get("channel") or "ecommerce",
            "device_id": payload.get("device_id"),
            "ip_country": (payload.get("ip_country") or "").upper() or None,
            "email_domain": email_domain,
            "created_at": timestamp,
            "context": payload.get("context") or {},
            "label": payload.get("label"),
            "pattern": payload.get("pattern"),
        }
        return event

    # ---------------------------------------------------------------- scoring
    def _record(
        self,
        event: dict[str, Any],
        features: dict[str, float],
        assessment: dict[str, Any],
        latency_ms: float,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        row = {
            "id": event["id"],
            "external_id": event["external_id"],
            "customer_id": event["customer_id"],
            "card_id": event["card_id"],
            "amount": event["amount"],
            "currency": event["currency"],
            "merchant_id": event["merchant_id"],
            "merchant_name": event["merchant_name"],
            "merchant_category": event["merchant_category"],
            "merchant_country": event["merchant_country"],
            "channel": event["channel"],
            "device_id": event["device_id"],
            "ip_country": event["ip_country"],
            "email_domain": event["email_domain"],
            "risk_score": assessment["risk_score"],
            "model_score": assessment["model_score"],
            "rule_score": assessment["rule_score"],
            "decision": assessment["decision"],
            "reason_codes": json.dumps(assessment["reasons"], separators=(",", ":")),
            "features": json.dumps({k: round(v, 4) for k, v in features.items()}, separators=(",", ":")),
            "model_version": assessment["model_version"],
            "latency_ms": round(latency_ms, 3),
            "label": event["label"],
            "created_at": event["created_at"],
            "scored_at": utcnow(),
        }

        alert = None
        if assessment["decision"] in {"review", "block"}:
            alert = {
                "id": f"alt_{uuid.uuid4().hex[:12]}",
                "transaction_id": row["id"],
                "severity": assessment["severity"],
                "risk_score": assessment["risk_score"],
                "status": "open",
                "assignee": None,
                "note": None,
                "created_at": event["created_at"],
                "updated_at": event["created_at"],
                "resolved_at": None,
            }
        return row, alert

    def score_event(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        started = time.perf_counter()
        event = self.normalize(payload)
        cfg = get_engine_config()
        features, meta = self.store.build(event)
        assessment = self.scorer.assess(event, features, meta, cfg)
        latency_ms = (time.perf_counter() - started) * 1000
        return self._record(event, features, assessment, latency_ms)

    def score_events(
        self, payloads: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Batch-scored ingest used by the historical backfill.

        Feature state is still advanced in event order, but the forest runs as a
        single matrix operation. This is the difference between a multi-minute
        cold start and a seed that finishes while the operator is still reading
        the boot log.
        """
        if not payloads:
            return [], []

        started = time.perf_counter()
        prepared: list[tuple[dict[str, Any], dict[str, float], dict[str, Any]]] = []
        for payload in payloads:
            event = self.normalize(payload)
            features, meta = self.store.build(event)
            prepared.append((event, features, meta))

        cfg = get_engine_config()
        model_scores = self.scorer.model_scores([item[1] for item in prepared])
        per_event_ms = (time.perf_counter() - started) * 1000 / max(len(prepared), 1)

        rows: list[dict[str, Any]] = []
        alerts: list[dict[str, Any]] = []
        for (event, features, meta), model_score in zip(prepared, model_scores):
            assessment = self.scorer.assess(
                event, features, meta, cfg, model_score=model_score
            )
            row, alert = self._record(event, features, assessment, per_event_ms)
            rows.append(row)
            if alert:
                alerts.append(alert)
        return rows, alerts

    # ---------------------------------------------------------------- process
    def process(
        self, payload: dict[str, Any], broadcast: bool = True, persist_sync: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        row, alert = self.score_event(payload)
        if persist_sync:
            self.writer.write_now(row, alert)
        else:
            self.writer.enqueue(row, alert)
        self._remember(row, alert)
        self._update_counters(row)
        self.last_event_at = to_iso(row["created_at"])

        if broadcast:
            summary = live_summary(row)
            summary["alert_id"] = alert["id"] if alert else None
            self.bus.publish("transaction", summary)
            if alert:
                self.bus.publish(
                    "alert",
                    {
                        "id": alert["id"],
                        "transaction_id": alert["transaction_id"],
                        "severity": alert["severity"],
                        "risk_score": alert["risk_score"],
                        "status": alert["status"],
                        "created_at": to_iso(alert["created_at"]),
                        "merchant_name": row["merchant_name"],
                        "amount": row["amount"],
                        "customer_id": row["customer_id"],
                    },
                )
            if row["decision"] == "block":
                dispatcher.submit(
                    {
                        **summary,
                        "alert_id": alert["id"] if alert else None,
                        "reasons": summary.get("reasons", []),
                    }
                )
        return row, alert

    # ------------------------------------------------------------------ cache
    def _remember(self, row: dict[str, Any], alert: dict[str, Any] | None) -> None:
        with self._lock:
            self._txn_cache[row["id"]] = row
            if len(self._txn_cache) > 2000:
                self._txn_cache.popitem(last=False)
            if alert:
                self._alert_cache[alert["id"]] = alert
                if len(self._alert_cache) > 2000:
                    self._alert_cache.popitem(last=False)

    def cached_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._txn_cache.get(transaction_id)

    def cached_alert(self, alert_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._alert_cache.get(alert_id)

    def _update_counters(self, row: dict[str, Any]) -> None:
        self.counters["total"] += 1
        self.counters[row["decision"]] += 1
        if row.get("label") == "fraud":
            self.counters["fraud_label"] += 1
        self._latencies.append(float(row["latency_ms"]))

    def latency_stats(self) -> dict[str, float]:
        if not self._latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
        values = sorted(self._latencies)
        return {
            "p50": round(values[int(len(values) * 0.5)], 2),
            "p95": round(values[min(int(len(values) * 0.95), len(values) - 1)], 2),
            "p99": round(values[min(int(len(values) * 0.99), len(values) - 1)], 2),
            "avg": round(sum(values) / len(values), 2),
        }

    def system_status(self) -> dict[str, Any]:
        return {
            "uptime_seconds": int(time.time() - self.started_at),
            "processed": self.counters["total"],
            "counters": dict(self.counters),
            "latency": self.latency_stats(),
            "last_event_at": self.last_event_at,
            "ingest_mode": settings.ingest_mode,
            "subscribers": self.bus.subscriber_count,
            "writer": self.writer.stats(),
            "model_version": self.scorer.card.get("version"),
        }

    def reset_state(self) -> None:
        with self._lock:
            self.store.clear()
            self._txn_cache.clear()
            self._alert_cache.clear()
            self._latencies.clear()
            for key in self.counters:
                self.counters[key] = 0
        self.started_at = time.time()
        self.last_event_at = None
