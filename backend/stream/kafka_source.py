"""Kafka / Redpanda ingestion.

The consumer runs in a daemon thread and hands each message to the scoring
pipeline. If the broker is unreachable the service either retries (production) or
falls back to the simulator (`INGEST_FALLBACK=simulator`), which is what makes the
public demo deployable without a broker.
"""

from __future__ import annotations

import json
import threading
import time

from backend.config import settings
from backend.core.logging import get_logger
from backend.stream.pipeline import TransactionPipeline
from backend.stream.simulator import Simulator

logger = get_logger("sentinel.kafka")


class KafkaSource:
    def __init__(self, pipeline: TransactionPipeline) -> None:
        self.pipeline = pipeline
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="kafka-consumer", daemon=True)
        self.connected = False
        self.consumed = 0
        self.last_error: str | None = None
        self.simulator: Simulator | None = None

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.simulator:
            self.simulator.stop()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        attempts = 0
        while not self._stop.is_set() and attempts < 3:
            attempts += 1
            try:
                from kafka import KafkaConsumer

                consumer = KafkaConsumer(
                    settings.kafka_topic,
                    bootstrap_servers=settings.kafka_bootstrap.split(","),
                    group_id=settings.kafka_group,
                    value_deserializer=lambda raw: json.loads(raw.decode("utf-8")),
                    auto_offset_reset="latest",
                    enable_auto_commit=True,
                    consumer_timeout_ms=1000,
                    request_timeout_ms=8000,
                )
                self.connected = True
                self.last_error = None
                logger.info("connected to kafka at %s topic=%s", settings.kafka_bootstrap, settings.kafka_topic)
                while not self._stop.is_set():
                    for message in consumer.poll(timeout_ms=500).values():
                        for record in message:
                            try:
                                self.pipeline.process(record.value)
                                self.consumed += 1
                            except Exception as exc:
                                logger.warning("bad kafka message skipped: %s", exc)
                consumer.close()
                return
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                logger.warning("kafka unavailable (attempt %d/3): %s", attempts, exc)
                time.sleep(min(2 * attempts, 6))

        if self._stop.is_set():
            return
        if settings.ingest_fallback == "simulator":
            logger.warning("falling back to in-process simulator")
            self.simulator = Simulator(self.pipeline, settings.simulator_tps)
            self.simulator.start()
        else:
            logger.error("kafka unavailable and no fallback configured; ingestion is idle")

    def status(self) -> dict:
        return {
            "mode": "kafka",
            "bootstrap": settings.kafka_bootstrap,
            "topic": settings.kafka_topic,
            "connected": self.connected,
            "consumed": self.consumed,
            "fallback": "simulator" if self.simulator else None,
            "last_error": self.last_error,
        }
