"""Audit trail.

Analyst actions and configuration changes are append-only. This is the minimum
required for any fraud operation that expects to defend a decision to a customer,
an auditor or a regulator.
"""

from __future__ import annotations

import json
from typing import Any

from backend.core.timeutil import utcnow
from backend.database import session_scope
from backend.models import AuditEvent


def record(
    action: str,
    entity_type: str,
    entity_id: str,
    actor: str = "system",
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        with session_scope() as session:
            session.add(
                AuditEvent(
                    actor=actor,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    metadata_json=json.dumps(metadata or {}),
                    created_at=utcnow(),
                )
            )
    except Exception:
        # Audit failures are logged by the exception middleware; they should not
        # abort the operator action itself.
        pass
