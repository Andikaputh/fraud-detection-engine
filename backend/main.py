"""Application entrypoint.

One process serves the JSON API, the SSE stream and the compiled console. That is
deliberate: it keeps deployment to a single container, avoids CORS in production
and lets a small hosting instance run the whole reference stack.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.router import api_router
from backend.api.runtime import runtime
from backend.config import settings
from backend.core.logging import configure_logging, get_logger
from backend.core.settings_store import load_settings
from backend.core.timeutil import utcnow
from backend.database import init_db
from backend.ml.scorer import get_scorer
from backend.services import analytics, audit, backfill
from backend.services.alerting import dispatcher
from backend.services.maintenance import RetentionWorker
from backend.services.seed import (
    is_seeded,
    seed_demo,
    sync_model_version,
    warm_state,
    wipe_all,
)
from backend.services.writer import TransactionWriter
from backend.stream.broadcaster import bus
from backend.stream.kafka_source import KafkaSource
from backend.stream.pipeline import TransactionPipeline
from backend.stream.simulator import Simulator

logger = get_logger("sentinel.app")
ROOT_DIR = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("starting %s v%s env=%s", settings.app_name, settings.version, settings.environment)
    started = time.time()

    init_db()
    load_settings(force=True)
    if settings.reset_on_start:
        logger.warning("RESET_ON_START enabled; clearing persisted data")
        wipe_all()

    writer = TransactionWriter()
    writer.start()
    runtime.writer = writer
    dispatcher.start()
    retention = RetentionWorker()
    retention.start()

    scorer = get_scorer()
    pipeline = TransactionPipeline(bus, writer)
    pipeline.scorer = scorer
    runtime.pipeline = pipeline
    bus.bind_loop(asyncio.get_running_loop())
    runtime.started_at = started

    seeded = is_seeded()
    needs_backfill = settings.seed_demo_data and not seeded
    if seeded:
        warm_state(pipeline)
        logger.info("warming aggregate cache")
        analytics.warm(pipeline)
    sync_model_version(scorer.card)

    if settings.ingest_mode == "simulator":
        runtime.simulator = Simulator(pipeline, settings.simulator_tps)
        if needs_backfill:
            # The API comes up immediately; the simulator waits for the seeded
            # feature state so live velocity does not race the backfill.
            runtime.simulator.pause()
        runtime.simulator.start()
    elif settings.ingest_mode == "kafka":
        if needs_backfill:
            seed_demo(pipeline, writer)
        runtime.kafka = KafkaSource(pipeline)
        runtime.kafka.start()
    elif settings.ingest_mode == "off":
        if needs_backfill:
            seed_demo(pipeline, writer)
        logger.info("ingestion disabled by configuration")
    else:
        logger.error("unknown INGEST_MODE=%s; expected simulator|kafka|off", settings.ingest_mode)

    if needs_backfill and settings.ingest_mode == "simulator":
        if not backfill.start(actor="system") and runtime.simulator:
            runtime.simulator.resume()

    audit.record(
        "engine.started",
        "environment",
        settings.environment,
        actor="system",
        metadata={
            "version": settings.version,
            "ingest_mode": settings.ingest_mode,
            "model_version": scorer.card.get("version"),
        },
    )
    logger.info("ready in %.2fs", time.time() - started)

    try:
        yield
    finally:
        logger.info("shutting down")
        if runtime.kafka:
            runtime.kafka.stop()
        if runtime.simulator:
            runtime.simulator.stop()
        retention.stop()
        writer.stop()
        dispatcher.stop()
        runtime.pipeline = None
        runtime.writer = None


def create_app() -> FastAPI:
    application = FastAPI(
        title="Sentinel Fraud Engine API",
        description=(
            "Real-time transaction risk scoring, alert triage and model observability. "
            "The console is served from the same origin at `/`."
        ),
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Operator", "Authorization"],
        expose_headers=["X-Request-ID", "Server-Timing"],
    )

    @application.middleware("http")
    async def request_metadata(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

    application.include_router(api_router)

    @application.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    def root():
        if DIST_DIR.exists():
            return FileResponse(DIST_DIR / "index.html")
        return JSONResponse(
            {
                "service": settings.app_name,
                "version": settings.version,
                "docs": "/docs",
                "health": "/api/v1/health",
                "console": "Run `npm run dev` in frontend/ for the console in development.",
            }
        )

    if DIST_DIR.exists():
        assets = DIST_DIR / "assets"
        if assets.exists():
            application.mount("/assets", StaticFiles(directory=assets), name="assets")

        @application.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            candidate = (DIST_DIR / full_path).resolve()
            if candidate.is_file() and DIST_DIR.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(DIST_DIR / "index.html")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
