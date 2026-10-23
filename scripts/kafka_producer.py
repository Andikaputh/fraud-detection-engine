"""Kafka producer for integration testing against a real broker.

Usage:
    python -m scripts.kafka_producer --bootstrap 127.0.0.1:9092 --tps 5
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from kafka import KafkaProducer

from backend.stream.world import World


def main() -> None:
    parser = argparse.ArgumentParser(description="Produce synthetic authorisations to Kafka")
    parser.add_argument("--bootstrap", default="127.0.0.1:9092")
    parser.add_argument("--topic", default="transaksi-finansial")
    parser.add_argument("--tps", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap.split(","),
        value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
        linger_ms=20,
    )
    world = World(seed=args.seed)
    print(f"producing to {args.bootstrap} topic={args.topic} tps={args.tps}")

    try:
        while True:
            payload = world.fraud_event(datetime.now(timezone.utc)) if world.rng.random() < 0.02 else world.normal_event(datetime.now(timezone.utc))
            producer.send(args.topic, value=payload)
            time.sleep(max(1.0 / args.tps, 0.01))
    except KeyboardInterrupt:
        producer.flush(timeout=10)
        print("stopped")


if __name__ == "__main__":
    main()
