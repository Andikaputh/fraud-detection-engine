"""Batched write path.

Inference must never wait for disk. Scored rows are appended to a bounded queue
and flushed by a single writer thread in batches (250 rows or 400 ms). This keeps
p99 latency stable during bursts and avoids one SQLite transaction per event.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from sqlalchemy.exc import IntegrityError

from backend.core.logging import get_logger
from backend.database import SessionLocal
from backend.models import Alert, Transaction

logger = get_logger("sentinel.writer")


class TransactionWriter:
    def __init__(self, batch_size: int = 250, flush_interval: float = 0.4, max_queue: int = 20_000):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self.written = 0
        self.alerts_written = 0
        self.dropped = 0
        self.failed_batches = 0
        self.last_flush_ms = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="txn-writer", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def enqueue(self, row: dict[str, Any], alert: dict[str, Any] | None = None) -> None:
        try:
            self.queue.put((row, alert), timeout=2.0)
        except queue.Full:
            self.dropped += 1
            logger.error("writer queue full; dropping transaction %s", row.get("id"))

    def enqueue_bulk(self, rows: list[dict[str, Any]], alerts: list[dict[str, Any]]) -> None:
        try:
            self.queue.put(("__bulk__", rows, alerts), timeout=30.0)
        except queue.Full:
            self.dropped += len(rows)
            logger.error("writer queue full during bulk insert; %d rows dropped", len(rows))

    def write_now(self, row: dict[str, Any], alert: dict[str, Any] | None = None) -> None:
        """Synchronous write for HTTP ingestion, where read-after-write matters."""
        self._flush([(row, alert)])

    def _run(self) -> None:
        batch: list[tuple[dict, dict | None]] = []
        bulk_rows: list[dict] = []
        bulk_alerts: list[dict] = []
        last_flush = time.monotonic()

        while not self._stop.is_set() or not self.queue.empty():
            timeout = max(0.02, self.flush_interval - (time.monotonic() - last_flush))
            try:
                item = self.queue.get(timeout=timeout)
            except queue.Empty:
                if batch:
                    self._flush(batch)
                    batch = []
                if bulk_rows:
                    self._flush_bulk(bulk_rows, bulk_alerts)
                    bulk_rows, bulk_alerts = [], []
                last_flush = time.monotonic()
                continue

            if isinstance(item[0], str) and item[0] == "__bulk__":
                if batch:
                    self._flush(batch)
                    batch = []
                _, rows, alerts = item
                self._flush_bulk(rows, alerts)
                self.queue.task_done()
                last_flush = time.monotonic()
                continue

            batch.append(item)  # type: ignore[arg-type]
            if len(batch) >= self.batch_size:
                self._flush(batch)
                batch = []
                last_flush = time.monotonic()
            self.queue.task_done()

        if batch:
            self._flush(batch)

    def _flush(self, batch: list[tuple[dict, dict | None]]) -> None:
        started = time.perf_counter()
        session = SessionLocal()
        try:
            session.add_all([Transaction(**row) for row, _ in batch])
            alerts = [alert for _, alert in batch if alert]
            if alerts:
                session.add_all([Alert(**alert) for alert in alerts])
            session.commit()
            self.written += len(batch)
            self.alerts_written += len(alerts)
        except IntegrityError:
            session.rollback()
            self.failed_batches += 1
            for row, alert in batch:
                try:
                    session.add(Transaction(**row))
                    if alert:
                        session.add(Alert(**alert))
                    session.commit()
                    self.written += 1
                    self.alerts_written += 1 if alert else 0
                except Exception as exc:  # duplicate or malformed row
                    session.rollback()
                    logger.warning("skipping row %s: %s", row.get("id"), exc)
        except Exception as exc:
            session.rollback()
            self.failed_batches += 1
            logger.error("write batch failed: %s", exc)
        finally:
            session.close()
            self.last_flush_ms = round((time.perf_counter() - started) * 1000, 2)

    def _flush_bulk(self, rows: list[dict], alerts: list[dict]) -> None:
        if not rows:
            return
        started = time.perf_counter()
        session = SessionLocal()
        try:
            # Core executemany avoids constructing 90k ORM instances during a
            # cold-start backfill. The web write path still uses the unit of work
            # so duplicate handling and alert rows stay transactional.
            session.execute(Transaction.__table__.insert(), rows)
            if alerts:
                session.execute(Alert.__table__.insert(), alerts)
            session.commit()
            self.written += len(rows)
            self.alerts_written += len(alerts)
        except IntegrityError:
            session.rollback()
            for row in rows:
                try:
                    session.execute(Transaction.__table__.insert(), [row])
                    session.commit()
                    self.written += 1
                except Exception:
                    session.rollback()
        except Exception as exc:
            session.rollback()
            logger.error("bulk write failed: %s", exc)
        finally:
            session.close()
            self.last_flush_ms = round((time.perf_counter() - started) * 1000, 2)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=15)

    def stats(self) -> dict:
        return {
            "queued": self.queue.qsize(),
            "written": self.written,
            "alerts_written": self.alerts_written,
            "dropped": self.dropped,
            "failed_batches": self.failed_batches,
            "last_flush_ms": self.last_flush_ms,
        }
