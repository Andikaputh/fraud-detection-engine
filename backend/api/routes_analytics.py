"""Dashboard aggregation endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.api.deps import get_pipeline
from backend.services import analytics

router = APIRouter()


@router.get("/overview")
def overview(window: str = Query(default="24h", pattern="^(1h|6h|24h|7d|30d)$")) -> dict[str, Any]:
    return analytics.build_overview(window, get_pipeline())


@router.get("/analytics")
def analytics_view(window: str = Query(default="7d", pattern="^(1h|6h|24h|7d|30d)$")) -> dict[str, Any]:
    return analytics.build_analytics(window, get_pipeline())
