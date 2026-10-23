# Sentinel Fraud Engine

**Real-time transaction risk decisioning, alert triage, and model observability as a single deployable application.**

**Live demo:** [sentinel-fraud-andikaputh.fly.dev](https://sentinel-fraud-andikaputh.fly.dev/) (Fly.io, Singapore; synthetic data)

Sentinel is the fraud decision layer for a fictional payments company, **Meridian Pay**. It ingests card-authorisation events, computes a behavioural anomaly score and an explainable policy score in the request path, returns `allow` / `review` / `block`, and persists the complete evidence behind every decision. The React console is an operations surface, not a dashboard bolted onto a notebook: alerts can be assigned and resolved, thresholds can be changed at runtime, historical data can be replayed, and the live feed is pushed over Server-Sent Events.

The repository contains the full working system: the FastAPI service, the anomaly model and rule engine, the simulator and optional Kafka adapter, the SQLite/Postgres persistence layer, the React 19 console, tests, a trained model artifact, a model card, and deployment files for Docker, Render, and Fly.io.

---

## Screenshots

### Overview

![Overview](docs/overview.png)

### Alert queue

![Alert queue](docs/alerts.png)

<details>
<summary>Analytics, model, and settings</summary>

### Analytics

![Analytics](docs/analytics.png)

### Model observability

![Model](docs/model.png)

### Settings

![Settings](docs/settings.png)

</details>

---

## What is actually implemented

| Area | Implementation |
| --- | --- |
| Decision API | FastAPI, Pydantic request contracts, synchronous scoring, structured reasons |
| Ingestion | Built-in transaction simulator (default), HTTP `POST /api/v1/transactions`, optional Kafka consumer |
| Streaming | Server-Sent Events with bounded per-subscriber queues and a polling fallback |
| Model | Isolation Forest (220 trees) with percentile calibration and a vectorised single-event evaluator |
| Policy layer | 15 deterministic rules with explicit weights and human-readable evidence |
| Scoring | `0.38 × model + 0.62 × rules`, agreement bonus, configurable review/block thresholds |
| Storage | SQLite WAL by default, PostgreSQL via `DATABASE_URL`, batched asynchronous writes |
| Alerting | Alert creation, severity, assignment, status transitions, audit history, Telegram/webhook delivery |
| Console | React 19, TypeScript, Vite, hand-written CSS, custom SVG charts, no charting dependency |
| Operations | Background historical backfill, live progress banner, retention worker, health/readiness, audit log |
| Deployment | Multi-stage Dockerfile, Compose, Render Blueprint, Fly.io config, Railway-style `Procfile` |
| Testing | 13 backend tests covering the API, scoring invariants, thresholds, and ingestion |

The default tenant and the transaction data are synthetic. There is no real card-network traffic, no PCI data, and no customer data in this repository.

---

## Architecture

```mermaid
flowchart LR
    subgraph Sources
        SIM[Simulator<br/>0.2 tps default]
        HTTP[POST /transactions]
        KAFKA[Kafka / Redpanda]
    end

    subgraph DecisionPlane[Decision plane]
        NORMALISE[Normalise<br/>UTC timestamp<br/>merchant / country]
        FEATURES[FeatureStore<br/>velocity, geo, device,<br/>customer baseline]
        MODEL[Isolation Forest<br/>220 trees]
        RULES[Policy rules<br/>weighted reasons]
        BLEND[Risk blend<br/>38% model / 62% rules]
        DECIDE{Thresholds<br/>review 60 / block 85}
    end

    subgraph Storage
        WRITER[Batched writer<br/>250 rows / 400 ms]
        DB[(SQLite WAL<br/>or Postgres)]
        AUDIT[(Audit events)]
    end

    subgraph Experience
        BUS[SSE event bus]
        API[JSON API]
        UI[React console]
        ALERTS[Telegram / webhook]
    end

    SIM --> NORMALISE
    HTTP --> NORMALISE
    KAFKA --> NORMALISE
    NORMALISE --> FEATURES --> MODEL --> BLEND
    FEATURES --> RULES --> BLEND
    BLEND --> DECIDE
    DECIDE --> WRITER --> DB
    DECIDE --> AUDIT
    DECIDE --> BUS --> UI
    DECIDE -->|review / block| ALERTS
    DB --> API --> UI
```

### Why one process

The JSON API, SSE stream, and compiled SPA are served by one FastAPI process. That keeps deployment to a single container, avoids CORS in production, and lets a small instance run the entire reference stack. The system is explicitly single-node: the in-process event bus and simulator assume one application process. Kafka is the ingress integration point; a production deployment should move the event bus to Redis/NATS and run multiple stateless scoring workers behind a load balancer.

---

## Decision path

### 1. Normalisation

Every event is normalised into a stable UTC timestamp, a merchant structure, an e-mail domain, and a canonical currency/country representation. Future timestamps are clamped to the current time so a bad producer cannot create events that break rolling windows.

### 2. Feature engineering

The feature store keeps per-card, per-customer, and per-device state:

| Feature | Meaning |
| --- | --- |
| `log_amount` | Log-transformed ticket size |
| `log_amount_ratio` | Ticket relative to the customer's historical average |
| `amount_z` | Standard deviations above the customer's typical ticket |
| `velocity_1m` / `velocity_10m` | Authorisations on the card in the last minute / ten minutes |
| `log_geo_speed` | Implied travel speed between consecutive merchants |
| `new_device` | Device not previously seen for the customer |
| `hour_sin` / `hour_cos` | Cyclical hour encoding in the customer's local timezone |
| `merchant_risk` | Merchant-category chargeback tier |
| `ip_country_mismatch` | IP country differs from both merchant and home country |
| `channel_risk` | Channel-level risk prior |
| `log_account_age` | Account age at decision time |
| `chargebacks` | Historical chargebacks on the customer profile |
| `distinct_countries_24h` | Distinct merchant countries in the last 24 hours |
| `is_disposable_email` | Temporary-mail provider detected |

The store is advanced in event order. The historical backfill uses the same path, so velocity and customer baselines are built exactly as they are for live events.

### 3. Model score

The shipped artifact is an Isolation Forest trained on 18,900 synthetic labelled rows with a 4.5% contamination target. The raw isolation score is calibrated against the training distribution:

- below the 99th percentile: linear mapping from the median to the 99th percentile;
- above the 99th percentile: linear mapping from the 99th to the 99.9th percentile;
- clipped to `[0, 100]`.

The hot path does not call `sklearn.decision_function` per event. Tree structure is copied into contiguous NumPy arrays once at startup and traversed level-by-level, which removes roughly 40 ms of Python overhead per call and matches the scikit-learn result exactly. Batch inference for the backfill uses a single BLAS-backed `decision_function` call.

Model card: [`artifacts/model_card.json`](artifacts/model_card.json). The runtime pins scikit-learn 1.9.0, the version used to train the committed artifact, so a container start does not emit unpickle-version warnings.

| Holdout metric | Value |
| --- | --- |
| ROC-AUC | 0.9801 |
| PR-AUC | 0.9450 |
| Precision at best F1 | 0.9059 |
| Recall at best F1 | 0.8662 |
| Best F1 | 0.8856 |
| TPR at 1% FPR | 0.83 |
| Holdout rows | 4,800 |

These are holdout metrics on synthetic data. They are useful for regression testing the model, not evidence of production fraud performance. Runtime precision and recall on the seeded console are lower because the displayed decision combines the model with the policy rules and because the generator deliberately over-represents fraud and edge cases.

### 4. Policy score

Rules are deterministic and individually weighted. Each hit is persisted with a code, label, weight, and human-readable detail.

| Rule | Weight | Trigger |
| --- | ---: | --- |
| `AMOUNT_ABOVE_THRESHOLD` | 35 | Amount at or above the configured sensitivity (default Rp 10,000,000) |
| `AMOUNT_RATIO_EXTREME` | 32 | Ticket ≥ 8× customer average and ≥ Rp 1,000,000 |
| `VELOCITY_1M` | 30 | ≥ 5 authorisations on the card in 60 seconds |
| `VELOCITY_10M` | 22 | ≥ 12 authorisations in 10 minutes |
| `CARD_TESTING` | 30 | ≥ 4 rapid low-value authorisations with no amount-ratio signal |
| `IMPOSSIBLE_TRAVEL` | 28 | > 50 km between merchants at > 900 km/h |
| `NEW_DEVICE_HIGH_VALUE` | 24 | New device with ≥ 2.5× normal spend or ≥ Rp 2,000,000 |
| `AMOUNT_DEVIATION` | 22 | ≥ 3 standard deviations above the customer's ticket |
| `HIGH_RISK_MERCHANT` | 18 | Merchant category risk tier ≥ 0.6 |
| `IP_COUNTRY_MISMATCH` | 14 | IP differs from merchant and customer home country |
| `UNUSUAL_HOUR` | 8 | Authorisation between 00:00 and 05:59 local time |
| `NEW_ACCOUNT` | 10 | Account younger than 7 days |
| `CHARGEBACK_HISTORY` | 12 | One or more prior chargebacks |
| `DISPOSABLE_EMAIL` | 12 | Temporary-mail domain |
| `MULTI_COUNTRY_24H` | 15 | Three or more merchant countries in 24 hours |

### 5. Risk blend and decision

```
risk = 0.62 × rule_score + 0.38 × model_score
if rule_score ≥ 60 and model_score ≥ 55: risk += 6   # independent agreement
if rule_score ≥ 80:                      risk += 4   # severe policy breach
risk = clamp(round(risk), 0, 100)

if risk ≥ block_threshold and auto_block: block
elif risk ≥ review_threshold:             review
else:                                     allow
```

Defaults are `review = 60`, `block = 85`, and `auto_block = true`. All three are runtime settings and are visible on the Settings page. Changing them does not rescore historical rows; it changes the policy applied to new decisions.

Severity is assigned at decision time:

- `critical`: risk ≥ 90, or risk ≥ 80 with ticket ≥ Rp 20,000,000;
- `high`: risk ≥ 70;
- `medium`: everything else that becomes an alert.

Every review or block produces an alert with the full transaction, reasons, features, and audit trail attached.

---

## Data and persistence

### Schema

- `transactions`: immutable decision record, including the raw feature vector, reason codes, model version, decision, label, and latency.
- `alerts`: queue state, including severity, status, assignee, note, and resolved timestamp.
- `audit_events`: append-only operator/system history for alerts, settings, reset, and ingestion.
- `engine_settings`: persisted thresholds and simulator rate.
- `model_versions`: active model metadata and metric snapshots.

### Write path

Scoring never waits for disk. Transactions and alerts are placed on a bounded queue and flushed by one writer thread in batches of 250 rows or every 400 ms. HTTP ingestion opts into a synchronous write so the response has read-after-write semantics. The historical backfill uses SQLAlchemy Core `executemany` inserts, which avoids constructing tens of thousands of ORM objects during a cold start.

SQLite runs in WAL mode with a tuned synchronous level. Queue overflow increments a dropped counter and is visible in the console. On a 512 MB host, watch memory during the initial backfill; the full seven-day seed peaks at roughly 430 MB RSS in local testing. A 1 GB instance is the recommended minimum for the complete demo dataset.

### Retention

A maintenance thread removes transactions, alerts, and audit rows older than `RETENTION_DAYS` every six hours. The default in the repository is 30 days; deployment files set 7 days to keep the demo bounded.

PostgreSQL is supported by changing `DATABASE_URL`. The schema is created on boot and does not depend on SQLite-specific SQL. Use a managed Postgres instance when the console is expected to survive restarts or run on more than one replica.

---

## Historical backfill

A fresh installation needs history for the charts, prior-period KPIs, and a populated alert queue. On first boot Sentinel starts the API immediately, starts the simulator **paused**, and seeds seven days of history at a uniform average of roughly 13,500 authorisations per day (about 94,000 rows after injected bursts). A consistent density matters: a dense recent block followed by a sparse tail creates a cliff in the 7-day chart and in daily model drift, which reads as an outage rather than a deliberate retention boundary.

The live simulator defaults to **0.2 authorisations/second**, slightly above the historical average, so the feed keeps moving while the seeded footprint stays bounded. The rate is configurable; bursts of 7-12 card-testing events are injected periodically to exercise velocity rules.

The backfill runs through the real feature store and scoring pipeline, not a synthetic INSERT of fake scores. It is a background thread. The console polls `/api/v1/backfill` and displays a progress banner with the number of authorisations scored. When the seed completes, the simulator resumes. A cold start therefore stays healthy within a second while the baseline fills in behind it.

The same job powers **Settings → Rebuild demo environment**, which clears the database and starts a fresh backfill. Both operations refuse to start concurrently.

Approximate local timings on the development machine used for the screenshots:

- API health on an empty database: < 1 second;
- full seven-day backfill: ~35-50 seconds;
- peak RSS during backfill: ~430 MB;
- database size after seed: ~140 MB;
- restart with an existing database: ~10-15 seconds while feature state and the two default aggregates are warmed.

These numbers are a development baseline, not an SLA. `SEED_DEMO_DATA=false` skips the seed entirely on memory-constrained hosts.

---

## API

Base path: `/api/v1`. Interactive documentation is available at `/docs` and `/redoc`.

Set `SENTINEL_API_KEY` to protect mutating endpoints. When set, send `X-API-Key: <key>` or `Authorization: Bearer <key>`. The console stores the key in local storage from the Settings page and attaches it to writes. GET endpoints and the console remain public in demo mode.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness and database status |
| `GET` | `/ready` | Readiness, including model and storage checks |
| `GET` | `/system` | Pipeline, writer, SSE, storage, and delivery status |
| `GET` | `/backfill` | Background seed/reset progress |
| `GET` | `/overview?window=24h` | KPIs, series, risk bands, merchants, channels, label metrics |
| `GET` | `/analytics?window=7d` | Decision volume, risk histogram, drift, reason mix, coverage |
| `GET` | `/transactions` | Paginated search with window, decision, risk, country, channel, and text filters |
| `GET` | `/transactions/{id}` | Transaction plus attached alert, with an in-memory read-after-write cache |
| `POST` | `/transactions` | Score and persist a single authorisation |
| `GET` | `/stream` | Server-Sent Events: `transaction`, `alert`, `settings.updated` |
| `GET` | `/alerts` | Paginated alert queue with status, severity, window, and search filters |
| `GET` | `/alerts/stats` | Queue counts, severity mix, oldest open, 24-hour closures |
| `GET` | `/alerts/{id}` | Alert, transaction, and audit history |
| `PATCH` | `/alerts/{id}` | Assign, annotate, or transition an alert |
| `GET` | `/settings` | Effective engine settings and integration status |
| `PATCH` | `/settings` | Update thresholds, amount sensitivity, velocity limits, simulator TPS |
| `GET` | `/model` | Model card, feature importance, calibration, versions |
| `POST` | `/model/score` | What-if scoring without persisting a transaction |
| `POST` | `/simulate/burst` | Generate a card-testing, account-takeover, stolen-card, or mixed burst |
| `POST` | `/demo/reset` | Start a background reset and backfill (demo mode only) |
| `GET` | `/audit` | Audit log with action and entity filters |

### Score a transaction

```bash
curl -X POST http://localhost:8000/api/v1/transactions \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SENTINEL_API_KEY" \
  -d '{
    "customer_id": "cus_demo_001",
    "card_id": "card_demo_001",
    "amount": 18500000,
    "currency": "IDR",
    "merchant": {
      "id": "mrc_29",
      "name": "CryptoBridge",
      "category": "crypto",
      "country": "US",
      "risk_tier": 0.9
    },
    "channel": "ecommerce",
    "device_id": "dev_new_001",
    "ip_country": "RU",
    "email": "demo@mailinator.com",
    "context": {
      "home_country": "ID",
      "account_age_days": 3,
      "chargebacks": 1,
      "avg_amount": 250000
    }
  }'
```

The response contains the decision, blended risk score, model and rule components, ordered reasons, features, model version, and latency.

### Subscribe to the live stream

```bash
curl -N http://localhost:8000/api/v1/stream
```

Each frame is a standard SSE event:

```text
event: transaction
data: {"type":"transaction","sequence":1842,"data":{...}}
```

Slow subscribers get the oldest queued frame dropped rather than back-pressuring ingestion. The console keeps polling the JSON API, so a missed SSE frame is not a correctness issue.

### Update an alert

```bash
curl -X PATCH http://localhost:8000/api/v1/alerts/alt_123 \
  -H "Content-Type: application/json" \
  -H "X-Operator: a.nugroho" \
  -d '{"status":"investigating","assignee":"a.nugroho","note":"Checking device history."}'
```

---

## Console

The console is a React 19 + TypeScript + Vite application served from the same origin as the API.

- **Overview**: rolling KPIs, authorisation/block/review series, risk-band donut, live transaction feed, active alerts, system health, top reasons, merchant exposure.
- **Alert queue**: default unresolved queue, severity/status tabs, search, time filters, assignment and status transitions, full evidence drawer, audit timeline.
- **Analytics**: decision volume, risk histogram, model drift by day, category performance, reason mix, label metrics with explicit synthetic-data caveat.
- **Model**: model card, holdout metrics, feature importance, calibration thresholds, version history, and a what-if scorer.
- **Settings**: review/block thresholds, amount sensitivity, velocity limits, auto-block, simulator rate, Telegram/webhook configuration, operator identity, API key, and demo reset.

The visual system is hand-written CSS with custom SVG charts. There is no chart library, no component framework, and no external runtime dependency beyond React, React Router, and a bundled Inter variable font.

Keyboard:

- `Cmd/Ctrl + K`: command palette.
- `Esc`: close palette, drawer, or toast.
- Time windows are URL-independent and reset on navigation by design; the alert `focus` parameter is preserved in the query string.

All timestamps are rendered in UTC, matching the clock in the top bar. Relative times (`2m ago`) are computed against the browser clock.

---

## Local development

### Prerequisites

- Python 3.11 or newer (the Docker image uses 3.12).
- Node.js 20 or newer (the Docker image uses 22).
- No Kafka, Redis, or external database is required for the default demo.

### Backend

```bash
python -m venv env
# Windows:
env\Scripts\activate
# macOS/Linux:
# source env/bin/activate

pip install -r requirements.txt
cp .env.example .env        # optional; defaults work without it

uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

The first boot creates `data/sentinel.db`, starts the background seed, and serves the API. Open `http://127.0.0.1:8000/docs` for the API and `http://127.0.0.1:8000` for the compiled console if `frontend/dist` exists.

To run the tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

To retrain the model:

```bash
python -m scripts.train_model
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`. Override with `VITE_API_PROXY`. For a production build:

```bash
npm run build
```

The build is written to `frontend/dist` and served by FastAPI. The repository does not require a separate Node server in production.

### Kafka mode

The default source is the simulator. To consume from Kafka/Redpanda:

```bash
# Start Redpanda and the app
docker compose --profile kafka up -d

# Produce demo events
python -m scripts.kafka_producer

# Point the app at the broker
INGEST_MODE=kafka KAFKA_BOOTSTRAP_SERVERS=redpanda:29092 docker compose up -d app
```

The consumer commits offsets and reconnects with backoff. `INGEST_FALLBACK=simulator` controls whether the service falls back to the simulator if Kafka is unavailable.

---

## Deployment

### Docker

```bash
docker build -t sentinel-fraud-engine .
docker run --rm -p 8000:8000 -v sentinel-data:/app/data sentinel-fraud-engine
```

The image is multi-stage: Node builds the console, Python runs the API and serves the compiled assets. It runs as a non-root user and exposes a health check on `/api/v1/health`.

Compose:

```bash
docker compose up -d --build
```

### Render (Blueprint)

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and connect the repository. Render reads [`render.yaml`](render.yaml).
3. Apply the blueprint. The service builds the Dockerfile and uses `/api/v1/health` as the health check.
4. Wait for the first deploy. The API is healthy immediately; the console shows the historical backfill progress banner while the seven-day baseline is scored.

The blueprint uses the free plan. Two constraints matter:

- Free instances have 512 MB RAM. The full backfill is close to that ceiling even with writer back-pressure. If the instance restarts during seeding, use a 1 GB plan, or deploy the supplied Fly.io configuration which uses a 1 GB machine.
- Free instances do not provide persistent disks. The SQLite database is ephemeral and is recreated after a restart or redeploy. That is acceptable for a portfolio demo; for persistence, attach a paid disk or set `DATABASE_URL` to managed Postgres.

### Fly.io

The reference deployment runs at **https://sentinel-fraud-andikaputh.fly.dev/** on a 1 GB machine in Singapore with a 1 GB volume.

```bash
fly auth login
fly apps create sentinel-fraud-andikaputh
fly volumes create sentinel_data --region sin --size 1
fly deploy --ha=false
fly status
```

For a fork, change `app` in [`fly.toml`](fly.toml) to a unique name, then use that name in `fly apps create` and `fly deploy --app <your-app-name> --ha=false`. The supplied [`fly.toml`](fly.toml) mounts a 1 GB volume at `/app/data`, uses a 1 GB machine, and keeps at least one machine running so the simulator stays live.

Optional secrets:

```bash
fly secrets set SENTINEL_API_KEY=change-me
fly secrets set TELEGRAM_TOKEN=... CHAT_ID=...
```

The app and volume already exist for the reference deployment. Routine updates need only `fly deploy --ha=false`. The config keeps one machine running to preserve the in-process simulator and SSE stream; check Fly billing for an always-on 1 GB machine.

### Railway / other PaaS

Use the Dockerfile directly, or use the included `Procfile` with a Python buildpack. Set:

```text
DATABASE_URL=postgresql+psycopg://...
SEED_DEMO_DATA=true
INGEST_MODE=simulator
RETENTION_DAYS=7
```

The process must run **one** Uvicorn worker. The SSE bus and simulator are in-process; running multiple workers behind a load balancer would split real-time subscribers and duplicate simulation.

### Persistent storage

SQLite on a mounted volume is sufficient for a single-instance demo. For anything that needs to survive multiple instances, use Postgres:

```text
DATABASE_URL=postgresql+psycopg://user:password@host:5432/sentinel
```

No migration step is required: the schema is created on boot. For production, replace `create_all` with Alembic migrations before changing the schema.

### Recommended hosting shape

| Setup | Suitable for |
| --- | --- |
| Fly.io, 1 GB, 1 volume | Best default for the full demo |
| Render Starter, 1 GB, disk or Postgres | Managed deployment with persistence |
| Render Free, 512 MB, ephemeral | UI/portfolio demo; expect re-seeding after restarts |
| Docker on a VPS | Full control; add TLS and a reverse proxy |
| Kubernetes / multi-replica | Requires replacing the in-process bus and simulator with shared infrastructure |

---

## Performance notes

The system is engineered for a modest but continuous stream, not for claims of horizontal scale.

- **Single-event path**: normalisation, feature update, forest traversal, rules, persistence decision. Local warm-process p50 is roughly 1.5-2 ms; p95 is around 3 ms when no aggregate scan is running. The console reports the live distribution.
- **Batch backfill**: one `decision_function` call per 6,000-row chunk, SQLAlchemy Core `executemany` writes, and queue back-pressure to keep RSS bounded.
- **SSE**: per-subscriber bounded queues; slow clients lose old frames instead of blocking scoring.
- **Write path**: 250-row batches or 400 ms flush, WAL mode, single writer thread.
- **Read path**: narrow column projections and per-view aggregate caches (30 seconds for overview, 120 seconds for analytics), warmed after a backfill and on restart. In-memory read-after-write is used for the HTTP ingestion response.
- **Retention**: a bounded cleanup job prevents unbounded SQLite growth.

A cold seven-day analytics scan takes a few seconds and shares the GIL with scoring in this single-process build, so tail latency can spike while it runs. The cache and warm-up keep that work off the normal first-page path; a production deployment should move read aggregations to a separate service or pre-aggregated tables. There is no load-test harness in the repository. The latency numbers above are development observations, not a production benchmark. A real deployment should add k6/Locust, p99 SLOs, database connection pooling, and a shared cache before making capacity claims.

---

## Security and production readiness

This is a portfolio-grade **reference implementation**, not a certified fraud platform.

Implemented:

- optional API-key protection for mutating endpoints;
- optional Telegram/webhook delivery;
- structured audit events;
- non-root container user;
- no secrets committed;
- input validation and bounded payload sizes;
- CORS restricted to configured origins;
- security headers on responses.

Not implemented:

- user accounts, RBAC, SSO, or tenant isolation;
- field-level encryption or tokenisation;
- PCI DSS controls;
- rate limiting at the edge;
- WAF/bot management;
- immutable audit storage or WORM retention;
- chargeback ingestion from a card network;
- case-management workflow beyond alert status and notes;
- four-eyes approval for threshold changes;
- Alembic migrations;
- multi-region or multi-replica coordination.

Do not process real card data with this repository as-is. If you adapt it, start by adding authentication and authorisation, a managed Postgres instance, secret management, a reverse proxy with TLS, and a formal threat model.

---

## Industry comparison

| Capability | Stripe Radar / Sift / Feedzai | Sentinel |
| --- | --- | --- |
| Real-time scoring | Yes | Yes |
| Explainable reasons | Yes | Yes, persisted with every decision |
| Alert triage | Yes | Yes, queue + status + assignment + audit |
| Model observability | Yes | Model card, calibration, drift, what-if |
| Threshold controls | Yes | Yes, runtime persisted settings |
| Network-scale features | Cross-merchant consortium signals | Per-tenant synthetic features only |
| Model training | Proprietary supervised + unsupervised ensembles | Single Isolation Forest + rules |
| Data ingestion | Card network / gateway integrations | HTTP, simulator, Kafka adapter |
| Case management | Full investigator workflows | Alert status, notes, audit |
| Compliance | PCI, SOC 2, regional controls | None claimed |
| Scale | Multi-region, sharded, stream processors | Single process, single writer |

The honest summary: Sentinel demonstrates the **shape** of a commercial fraud platform, covering decisioning, evidence, triage, observability, and deployment, while deliberately stopping at the boundaries where a real platform needs organisational, regulatory, and infrastructure work.

---

## Repository layout

```text
.
├── backend/
│   ├── api/                 # FastAPI routers, dependencies, runtime handles
│   ├── core/                # settings store, logging, time helpers
│   ├── ml/                  # features, rules, scorer, trainer
│   ├── services/            # seed, backfill, writer, analytics, alerting, audit, retention
│   ├── stream/              # simulator, Kafka source, pipeline, SSE bus, world generator
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   └── main.py              # lifespan, background workers, SPA serving
├── frontend/
│   ├── src/components/      # layout, charts, drawers, palette, toasts, UI primitives
│   ├── src/pages/           # overview, alerts, analytics, model, settings
│   ├── src/lib/             # API client, SSE context, formatting, hooks
│   └── src/index.css        # design system
├── artifacts/               # trained model + model card
├── scripts/                 # training and Kafka producer CLIs
├── tests/                   # API and scoring tests
├── docs/                    # screenshots
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── fly.toml
├── Procfile
├── requirements.txt
└── .env.example
```

---

## Troubleshooting

**The console shows a backfill banner for a minute.** That is expected on a fresh database. The API is already healthy; the seed is scoring historical events in the background.

**The dashboard is empty after a restart.** On an ephemeral host, the SQLite volume was lost. Either attach a persistent volume, use Postgres, or wait for the automatic re-seed.

**`writer queue full` appears in the logs.** The ingestion rate exceeded the writer's drain rate. Reduce the simulator TPS, batch more aggressively, or move to Postgres. The dropped counter is exposed in `/system`.

**Alerts are not delivered to Telegram.** Check `TELEGRAM_TOKEN` and `CHAT_ID`. Delivery failures are deliberately non-fatal for scoring; inspect `/system` and the application log.

**The model artifact is missing.** Run `python -m scripts.train_model`. On boot, `ensure_artifact` can train a fallback model, but a supplied artifact is faster and reproducible.

**Multiple Uvicorn workers break the live feed.** Run one worker. SSE subscribers and the simulator are process-local.

---

## License and attribution

No license file is included. Add one before redistributing or using this repository commercially. The model, data generator, UI, and copy are original work created for this project.

The product name, tenant, merchants, customers, and transactions are fictional. Any resemblance to a real payment company is coincidental.
