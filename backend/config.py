"""Runtime configuration.

Values are read once at import time from the environment (optionally via `.env`).
The service is designed to run with zero configuration in demo mode; every
knob has a sensible default so a container can be started with no env vars.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_name: str = "Sentinel Fraud Engine"
    service_name: str = "sentinel-api"
    version: str = "1.0.0"
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    demo_mode: bool = field(default_factory=lambda: _bool("DEMO_MODE", True))

    # Ingestion
    ingest_mode: str = field(default_factory=lambda: os.getenv("INGEST_MODE", "simulator").lower())
    ingest_fallback: str = field(
        default_factory=lambda: os.getenv("INGEST_FALLBACK", "simulator").lower()
    )
    kafka_bootstrap: str = field(
        default_factory=lambda: os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")
    )
    kafka_topic: str = field(
        default_factory=lambda: os.getenv("KAFKA_TOPIC", "transaksi-finansial")
    )
    kafka_group: str = field(default_factory=lambda: os.getenv("KAFKA_GROUP", "sentinel-scoring-v1"))
    simulator_tps: float = field(default_factory=lambda: _float("SIMULATOR_TPS", 0.2))
    simulator_seed: int = field(default_factory=lambda: _int("SIMULATOR_SEED", 0))

    # Data
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{(ROOT_DIR / 'data' / 'sentinel.db').as_posix()}")
    )
    seed_demo_data: bool = field(default_factory=lambda: _bool("SEED_DEMO_DATA", True))
    reset_on_start: bool = field(default_factory=lambda: _bool("RESET_ON_START", False))
    retention_days: int = field(default_factory=lambda: _int("RETENTION_DAYS", 30))
    # The full seven-day baseline is useful locally but too heavy for a 512 MB
    # free instance. Small hosts can lower the row count without changing the
    # time windows or the scoring path.
    seed_history_rows: int = field(default_factory=lambda: _int("SEED_HISTORY_ROWS", 92_400))
    seed_history_days: int = field(default_factory=lambda: _int("SEED_HISTORY_DAYS", 7))

    # Model
    model_dir: Path = field(default_factory=lambda: Path(os.getenv("MODEL_DIR", str(ROOT_DIR / "artifacts"))))
    model_version: str = field(default_factory=lambda: os.getenv("MODEL_VERSION", "iforest-2026.02"))

    # Integrations
    telegram_token: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN") or None)
    telegram_chat_id: str | None = field(default_factory=lambda: os.getenv("CHAT_ID") or None)
    alert_webhook_url: str | None = field(default_factory=lambda: os.getenv("ALERT_WEBHOOK_URL") or None)
    public_base_url: str | None = field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL") or None)

    # Security / ops
    api_key: str | None = field(default_factory=lambda: os.getenv("SENTINEL_API_KEY") or None)
    cors_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if origin.strip()
        ]
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    max_live_buffer: int = field(default_factory=lambda: _int("MAX_LIVE_BUFFER", 500))
    stream_queue_size: int = field(default_factory=lambda: _int("STREAM_QUEUE_SIZE", 256))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def artifacts_ready(self) -> bool:
        return (self.model_dir / "model.joblib").exists()


settings = Settings()
