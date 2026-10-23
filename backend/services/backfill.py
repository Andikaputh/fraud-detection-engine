"""Background historical backfill.

Seeding tens of thousands of labelled events through the real scoring pipeline is
useful but must not hold the HTTP server hostage during a container cold start.
The worker below advances the feature store, writes in batches, and exposes
progress through the runtime object so the console can explain what is
happening instead of showing an empty dashboard.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from backend.api.runtime import runtime
from backend.core.logging import get_logger
from backend.services import analytics, audit
from backend.services.seed import HISTORY_ROWS, reset_demo, seed_demo

logger = get_logger("sentinel.backfill")


def is_running() -> bool:
    return runtime.seeding


def start(*, reset: bool = False, actor: str = "system") -> bool:
    """Start a seed/reset job. Returns False when one is already running."""
    if runtime.seeding:
        return False
    pipeline = runtime.pipeline
    writer = runtime.writer
    if pipeline is None or writer is None:
        return False

    runtime.seeding = True
    runtime.seed_progress = 0
    runtime.seed_total = HISTORY_ROWS
    runtime.seed_started_at = time.time()
    runtime.seed_error = None
    runtime.seed_summary = None

    if runtime.simulator:
        runtime.simulator.pause()

    def progress(done: int, total: int) -> None:
        runtime.seed_progress = done
        runtime.seed_total = total

    def run() -> None:
        try:
            writer.queue.join()
            summary = (
                reset_demo(pipeline, writer, on_progress=progress)
                if reset
                else seed_demo(pipeline, writer, on_progress=progress)
            )
            runtime.seed_summary = summary
            analytics.invalidate_cache()
            audit.record(
                "demo.reset.completed" if reset else "engine.backfilled",
                "environment",
                "demo",
                actor=actor,
                metadata=summary,
            )
            # Keep the first dashboard visit fast. Ingestion is still paused here,
            # so the aggregation cannot distort the live scoring latency sample.
            analytics.warm(pipeline)
            logger.info("backfill complete: %s", summary)
        except Exception as exc:  # keep the service alive; surface the failure in the console
            runtime.seed_error = str(exc)
            logger.exception("backfill failed: %s", exc)
        finally:
            runtime.seeding = False
            if runtime.simulator:
                runtime.simulator.resume()

    thread = threading.Thread(target=run, name="history-backfill", daemon=True)
    thread.start()
    return True


def snapshot() -> dict[str, Any]:
    return runtime.backfill_status()
