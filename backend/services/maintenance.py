"""Bounded retention for the demo database.

SQLite is the default deployment store, so an always-on stream would otherwise
grow without limit. A single maintenance thread removes rows older than
``RETENTION_DAYS`` every few hours; deletes are ordered so the console never
shows an alert without its transaction.
"""

from __future__ import annotations

import threading
from datetime import timedelta

from backend.api.runtime import runtime
from backend.config import settings
from backend.core.logging import get_logger
from backend.core.timeutil import utcnow
from backend.database import session_scope
from backend.models import Alert, AuditEvent, Transaction
from backend.services import analytics

logger = get_logger("sentinel.retention")


class RetentionWorker:
    def __init__(self, interval_seconds: int = 21_600, initial_delay: int = 120) -> None:
        self.interval = interval_seconds
        self.initial_delay = initial_delay
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="retention", daemon=True)
        self.last_deleted = 0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        if self._stop.wait(self.initial_delay):
            return
        while not self._stop.is_set():
            try:
                if not runtime.seeding:
                    self.prune()
            except Exception as exc:  # maintenance must never stop the API
                logger.exception("retention pass failed: %s", exc)
            self._stop.wait(self.interval)

    def prune(self) -> int:
        cutoff = utcnow() - timedelta(days=settings.retention_days)
        with session_scope() as session:
            alerts = session.query(Alert).filter(Alert.created_at < cutoff).delete(synchronize_session=False)
            transactions = (
                session.query(Transaction)
                .filter(Transaction.created_at < cutoff)
                .delete(synchronize_session=False)
            )
            audits = (
                session.query(AuditEvent)
                .filter(AuditEvent.created_at < cutoff)
                .delete(synchronize_session=False)
            )
        deleted = alerts + transactions + audits
        if deleted:
            self.last_deleted = deleted
            analytics.invalidate_cache()
            logger.info(
                "retention removed %d transactions, %d alerts and %d audit rows older than %s",
                transactions,
                alerts,
                audits,
                cutoff.date().isoformat(),
            )
        return deleted
