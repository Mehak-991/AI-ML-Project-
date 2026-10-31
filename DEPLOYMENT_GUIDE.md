# Production Deployment Guide: AI/ML Management Platform (Phase 15)

This guide documents the containerized production architecture, deployment instructions, volume management, and disaster recovery procedures.

---

## 1. Architecture Overview

The platform uses a modular container architecture orchestrated via Docker Compose:

1. **`db` (PostgreSQL 18)**:
   - High-performance, ACID-compliant database.
   - Internal network only (no public ports exposed).
   - Health checked via `pg_isready`.
   - Data persisted to the `pgdata` volume.

2. **`migration` (One-off Alembic container)**:
   - Waits for database health check.
   - Runs `alembic upgrade head` (Revisions 0001–0007).
   - Terminates with status 0 upon completion before API/Worker start.

3. **`app` (FastAPI Production ASGI)**:
   - Multi-stage, non-root user (`app:app` uid 10001).
   - Uvicorn ASGI server with `--workers 2`, structured JSON logging, and graceful shutdown.
   - Connects to internal database network and frontend reverse-proxy network.
   - Persistent volume mounts for artifacts and datasets.

4. **`worker` (Dedicated Background Worker)**:
   - Standalone process executing `python scripts/run_worker.py`.
   - Continually claims queued long-running ML tasks (training, drift analysis, SHAP/LIME, batch predictions).
   - ThreadPool isolation from API web event loops.
   - Shares the same code base and persistent volume storage as `app`.

5. **`frontend` (React + Nginx)**:
   - Multi-stage build (Node 22 build -> Nginx 1.27 Alpine runtime).
   - Serves pre-compressed static SPA assets with 1-year immutable caching.
   - Reverse proxies `/api/`, `/docs`, `/openapi.json` to the internal `app:8000` service.
   - SPA fallback `try_files $uri $uri/ /index.html`.
   - Container health check via `/healthz`.

---

## 2. Prerequisites

- Docker 24+ and Docker Compose v2.20+
- Host system with at least 4 GB RAM and 10 GB disk space
- Valid environment configuration (`.env`)

---

## 3. Environment Setup

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Configure required production variables:
   ```ini
   POSTGRES_USER=aiproject
   POSTGRES_PASSWORD=<strong_random_database_password>
   POSTGRES_DB=aiproject

   # JWT Auth (Phase 10)
   JWT_SECRET_KEY=<generate_with_openssl_rand_-hex_32>
   JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
   JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

   # Storage & Networking
   APP_ENV=production
   DEBUG=false
   LOG_FORMAT=json
   FRONTEND_PORT=80
   ```

---

## 4. Startup & Deployment Commands

### Build & Launch Stack:
```bash
docker compose up -d --build
```

### Inspect Container Health:
```bash
docker compose ps
```
Expected output:
- `db`: Up (healthy)
- `migration`: Exited (0)
- `app`: Up (healthy)
- `worker`: Up
- `frontend`: Up (healthy)

### Stream Logs:
```bash
# All services
docker compose logs -f

# Backend API
docker compose logs -f app

# Background Worker
docker compose logs -f worker
```

---

## 5. Persistent Volume Mapping

| Volume Name | Container Path | Purpose |
|---|---|---|
| `pgdata` | `/var/lib/postgresql/data` | PostgreSQL database files & WAL logs |
| `uploads` | `/data/uploads` | Uploaded raw CSV/Excel dataset files |
| `models` | `/data/trained_models` | Serialized joblib/pickle model pipelines & metadata |
| `model_cache`| `/data/model_cache` | Cached transformer & tokenization weights |

---

---

## 6. Observability & Prometheus Metrics

The platform provides standard OpenMetrics / Prometheus exporter endpoint at `/metrics`:

- **Endpoint**: `GET /metrics`
- **Output Content-Type**: `text/plain; version=0.0.4; charset=utf-8`
- **Key Metric Families**:
  - `aiml_models_total`: Total number of registered machine learning models (gauge)
  - `aiml_jobs_by_status`: Count of background jobs partitioned by status (`queued`, `running`, `completed`, `failed`, `cancelled`, `retry_pending`) (gauge)
  - `aiml_predictions_total`: Total prediction requests processed partitioned by outcome status (counter)
  - `aiml_prediction_records_total`: Total individual records predicted across requests (counter)
  - `aiml_prediction_duration_ms_avg`: Average prediction duration in milliseconds by status (gauge)
  - `aiml_worker_health_status`: Dedicated background worker heartbeat liveness status (`1` = healthy, `0` = stale/dead) (gauge)

---

## 7. Automated Backup & Safe Restore Procedures

### Automated Backup Creation:
Executes non-blocking `pg_dump`, gzip compresses output, writes a SHA-256 sidecar file, records JSON metadata, and automatically enforces retention (default: keeps the last 7 daily backups, never deleting the only remaining backup):
```bash
python scripts/backup_db.py --retention 7
```

### Checksum Verification (Pre-Restore Validation):
Validates SHA-256 integrity against the recorded sidecar without modifying any database:
```bash
python scripts/restore_db.py --backup backups/db_backup_aiproject_<timestamp>.sql.gz --verify-only
```

### Isolated Test Restore (Disaster Recovery Drill):
Restores into a separate isolated test database to verify backup integrity safely:
```bash
python scripts/restore_db.py --backup backups/db_backup_aiproject_<timestamp>.sql.gz --target-db aiproject_test_restore --confirm
```

---

## 8. Versioning, Rollback & Deployment Hardening

### Docker Image Versioning:
All service images are versioned via the `${APP_VERSION}` environment variable (default: `0.4.0`):
```bash
APP_VERSION=0.4.0 docker compose up -d
```

### Rollback Runbook:
To rollback to a previous version without affecting volumes or database records:
```bash
# 1. Select target previous image tag or checkout release commit
APP_VERSION=0.3.0 docker compose up -d app worker frontend

# 2. Verify health
docker compose ps
curl http://localhost/health
```

