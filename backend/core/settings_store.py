"""Engine configuration persisted in the database.

Thresholds must survive a restart and be visible to every worker, so they live in
`engine_settings` rather than process memory. A process-local cache keeps the hot
scoring path free of database reads; writes update the cache under a lock.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from backend.config import settings as app_settings
from backend.core.timeutil import utcnow
from backend.database import session_scope
from backend.models import EngineSetting

DEFAULTS: dict[str, Any] = {
    "review_threshold": 60,
    "block_threshold": 85,
    "amount_sensitivity": 10_000_000.0,
    "velocity_limit_1m": 5,
    "velocity_limit_10m": 12,
    "auto_block": True,
    "telegram_enabled": False,
    # The environment is the source of truth until an operator saves an override
    # in the database. That keeps container configuration predictable.
    "simulator_tps": float(app_settings.simulator_tps),
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _coerce(key: str, raw: str) -> Any:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return raw.lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(float(raw))
    if isinstance(default, float):
        return float(raw)
    return raw


def load_settings(force: bool = False) -> dict[str, Any]:
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache
        values = dict(DEFAULTS)
        try:
            with session_scope() as session:
                for row in session.query(EngineSetting).all():
                    if row.key in DEFAULTS:
                        try:
                            values[row.key] = _coerce(row.key, row.value)
                        except (TypeError, ValueError):
                            continue
        except Exception:
            # A cold database must not stop the API from booting. Defaults apply
            # until the next successful read.
            pass
        _cache = values
        return _cache


def get_engine_config() -> dict[str, Any]:
    return load_settings()


def update_settings(patch: dict[str, Any], actor: str = "operator") -> dict[str, Any]:
    global _cache
    cleaned = {k: v for k, v in patch.items() if k in DEFAULTS and v is not None}
    if cleaned:
        now = utcnow()
        with session_scope() as session:
            for key, value in cleaned.items():
                row = session.get(EngineSetting, key)
                payload = json.dumps(value) if isinstance(value, bool) else str(value)
                if row:
                    row.value = payload
                    row.updated_at = now
                else:
                    session.add(EngineSetting(key=key, value=payload, updated_at=now))
    with _lock:
        _cache = None
    return load_settings(force=True)


def public_settings() -> dict[str, Any]:
    """Engine config enriched with non-secret integration status."""
    from backend.config import settings as app_settings

    values = dict(load_settings())
    values["telegram_configured"] = bool(app_settings.telegram_token and app_settings.telegram_chat_id)
    values["webhook_configured"] = bool(app_settings.alert_webhook_url)
    values["ingest_mode"] = app_settings.ingest_mode
    return values
