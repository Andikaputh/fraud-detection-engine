# syntax=docker/dockerfile:1.7

# --------------------------------------------------------------------------- UI
FROM node:22-alpine AS console
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libgomp is required by the scikit-learn wheel. Everything else is a pure wheel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --shell /usr/sbin/nologin sentinel
COPY --chown=sentinel:sentinel backend ./backend
COPY --chown=sentinel:sentinel artifacts ./artifacts
COPY --chown=sentinel:sentinel scripts ./scripts
COPY --from=console --chown=sentinel:sentinel /build/frontend/dist ./frontend/dist
RUN mkdir -p /app/data && chown -R sentinel:sentinel /app/data

ENV ENVIRONMENT=production \
    DEMO_MODE=true \
    INGEST_MODE=simulator \
    INGEST_FALLBACK=simulator \
    SIMULATOR_TPS=0.2 \
    SEED_DEMO_DATA=true \
    RETENTION_DAYS=7 \
    DATABASE_URL=sqlite:////app/data/sentinel.db \
    MODEL_DIR=/app/artifacts \
    PORT=8000

USER sentinel
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/health', timeout=4)"

CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
