"""Continuous transaction simulator.

The simulator is a first-class ingestion source, not a test fixture. It lets the
project run on a host with no Kafka cluster while still exercising the same
pipeline. `INGEST_MODE=simulator` is the default for that reason.
"""

from __future__ import annotations

import random
import threading
import time

from backend.core.logging import get_logger
from backend.core.settings_store import get_engine_config
from backend.core.timeutil import utcnow
from backend.stream.pipeline import TransactionPipeline
from backend.stream.world import World

logger = get_logger("sentinel.simulator")


class Simulator:
    def __init__(self, pipeline: TransactionPipeline, tps: float = 3.0) -> None:
        self.pipeline = pipeline
        self.world = World(seed=None)
        self.rng = random.Random()
        self._tps = tps
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread = threading.Thread(target=self._run, name="txn-simulator", daemon=True)
        self.emitted = 0
        self.next_burst_at = time.monotonic() + self.rng.uniform(75, 150)

    def start(self) -> None:
        self._thread.start()

    @property
    def tps(self) -> float:
        return self._tps

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def pause(self) -> None:
        self._pause.set()

    def resume(self) -> None:
        self._pause.clear()

    def _run(self) -> None:
        logger.info("simulator started at %.1f tps", self._tps)
        while not self._stop.is_set():
            if self._pause.is_set():
                time.sleep(0.2)
                continue
            cfg = get_engine_config()
            tps = float(cfg.get("simulator_tps", self._tps))
            self._tps = tps

            try:
                now = time.time()
                if now >= self.next_burst_at:
                    count = self.rng.randint(7, 12)
                    for payload in self.world.card_testing_burst(utcnow(), count):
                        self.pipeline.process(payload)
                        self.emitted += 1
                    self.next_burst_at = now + self.rng.uniform(120, 240)
                elif self.rng.random() < 0.018:
                    self.pipeline.process(self.world.fraud_event(utcnow()))
                    self.emitted += 1
                else:
                    high_value = self.rng.random() < 0.012
                    self.pipeline.process(self.world.normal_event(utcnow(), high_value=high_value))
                    self.emitted += 1
            except Exception as exc:  # keep the demo alive across transient failures
                logger.exception("simulator event failed: %s", exc)

            time.sleep(max(1.0 / max(tps, 0.2), 0.02) * self.rng.uniform(0.85, 1.15))

    def burst(self, pattern: str, count: int) -> int:
        events = self.world.burst(pattern, count, utcnow())
        for payload in events:
            self.pipeline.process(payload)
            self.emitted += 1
        return len(events)
