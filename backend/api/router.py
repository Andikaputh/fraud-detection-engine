from fastapi import APIRouter

from backend.api import routes_alerts, routes_analytics, routes_core, routes_transactions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(routes_core.router, tags=["operations"])
api_router.include_router(routes_transactions.router, tags=["transactions"])
api_router.include_router(routes_alerts.router, tags=["alerts"])
api_router.include_router(routes_analytics.router, tags=["analytics"])
