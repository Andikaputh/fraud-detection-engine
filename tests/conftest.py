"""Test bootstrap.

Environment is configured before the backend modules are imported because the
settings dataclass is evaluated at import time (the same way a container starts).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="sentinel-tests-"))
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(TEST_ROOT / 'test.db').as_posix()}",
        "MODEL_DIR": str(TEST_ROOT / "artifacts"),
        "INGEST_MODE": "off",
        "SEED_DEMO_DATA": "false",
        "DEMO_MODE": "true",
        "TELEGRAM_TOKEN": "",
        "CHAT_ID": "",
        "ALERT_WEBHOOK_URL": "",
        "SENTINEL_API_KEY": "",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
