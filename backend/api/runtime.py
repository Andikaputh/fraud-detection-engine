"""Process-wide runtime handles shared by the HTTP layer and background workers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.services.writer import TransactionWriter
    from backend.stream.kafka_source import KafkaSource
    from backend.stream.pipeline import TransactionPipeline
    from backend.stream.simulator import Simulator


class Runtime:
    pipeline: "TransactionPipeline | None" = None
    writer: "TransactionWriter | None" = None
    simulator: "Simulator | None" = None
    kafka: "KafkaSource | None" = None
    started_at: float = 0.0

    seeding: bool = False
    seed_progress: int = 0
    seed_total: int = 0
    seed_started_at: float | None = None
    seed_error: str | None = None
    seed_summary: dict[str, Any] | None = None

    def require_pipeline(self) -> "TransactionPipeline":
        if self.pipeline is None:
            raise RuntimeError("pipeline not initialised")
        return self.pipeline

    def backfill_status(self) -> dict[str, Any]:
        progress = min(self.seed_progress, self.seed_total) if self.seed_total else 0
        percent = round(progress / self.seed_total * 100, 1) if self.seed_total else None
        elapsed = int(time.time() - self.seed_started_at) if self.seed_started_at else 0
        return {
            "active": self.seeding,
            "progress": progress,
            "total": self.seed_total,
            "percent": percent,
            "elapsed_seconds": elapsed,
            "error": self.seed_error,
            "summary": self.seed_summary,
        }


runtime = Runtime()
