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

   # JWT Auth. Production refuses to start with the default or a < 32-byte secret.
   JWT_SECRET_KEY=<generate_with_openssl_rand_-hex_32>
   JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
   JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

   # Storage & Networking
   APP_ENV=production
   DEBUG=false
   LOG_FORMAT=json
   FRONTEND_PORT=80
   CORS_ORIGINS=https://your-domain.example

   # Optional hardening
   METRICS_AUTH_TOKEN=<random_token_for_prometheus>
   DOCS_ENABLED=false

   # Local LLM (only with `--profile llm`); no API keys are used anywhere
   OLLAMA_MODEL=llama3.2:3b
   OLLAMA_NUM_CTX=4096
   ```

3. Validate before starting: `python scripts/check_config.py --db` (or inside the container:
   `docker compose run --rm app python scripts/check_config.py --db`).

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

---

## 8. Versioning, Rollback & Deployment Hardening

### Docker Image Versioning:
All service images are versioned via the `${APP_VERSION}` environment variable (default: `0.4.0`):
```bash
APP_VERSION=0.4.0 docker compose up -d
```

### Container Hardening Controls:
- **Non-Root Execution**: Unprivileged service user `app` (`uid=10001`, `gid=10001`).
- **Capability Dropping**: `cap_drop: [ALL]` applied to backend API and worker processes.
- **Privilege Escalation Prevention**: `security_opt: ["no-new-privileges:true"]`.
- **Read-Only Root Filesystem**: `read_only: true` enabled on `app` and `worker`. Transient write locations are constrained to ephemeral in-memory tmpfs (`/tmp:size=256m,mode=1777,noexec,nosuid`).
- **Network Segmentation**: Internal `backend` network with strict isolation from host interfaces. Only reverse-proxy frontend exposes public HTTP/HTTPS ports.

### Rollback Runbook:
To rollback to a previous version without affecting volumes or database records:
```bash
# 1. Select target previous image tag or checkout release commit
APP_VERSION=0.3.0 docker compose up -d app worker frontend

# 2. Verify health
docker compose ps
curl http://localhost/health
```

---

## 9. Background Worker Fault Tolerance & Stalled-Job Recovery

### Automated Lease & Liveness Tracking:
Each background job claimed by a worker acquires an atomic lease:
- `worker_id`: Worker process identity (`host:pid:uuid`).
- `heartbeat_at`: Live timestamp refreshed continuously during processing.
- `SELECT FOR UPDATE SKIP LOCKED`: Prevents multiple workers from claiming or executing the same task.

### Stalled-Job Reaper Lifecycle:
If an execution host crashes, reboots, or receives an ungraceful termination signal:
1. **Startup Reaper**: The background worker scans `WHERE status = 'running'` for abandoned tasks upon startup.
2. **Periodic Sweep**: The worker re-checks for stalled jobs every `JOB_REAPER_INTERVAL_SECONDS` (default: 300s).
3. **Safe Re-Queuing**: Jobs with `retry_count < max_retries` are reset to `retry_pending` without corrupting results.
4. **Exhausted Jobs**: Permanently dead tasks exceeding retry quotas are marked `failed` with diagnostic error categories.

---

## 10. Performance Benchmarking & Scaling Guidance

### Verified ML Inference Throughput (scikit-learn LogisticRegression):
- **Single-record Latency**: P50 = 27.8 ms, P95 = 55.4 ms (cached pipeline).
- **Batch 10 Records**: P50 = 26.7 ms (~374 records/sec).
- **Batch 50 Records**: P50 = 34.4 ms (~1,455 records/sec).
- **Batch 100 Records**: P50 = 71.8 ms (~1,393 records/sec).
- **Batch 500 Records**: P50 = 82.5 ms (~6,059 records/sec).

### Database Query Optimization:
- **Composite Index**: `ix_prediction_logs_model_id_created_at` on `prediction_logs(model_id, created_at)` eliminates in-memory sorting on paginated audit logs.
- **Connection Pool Capacity**: Default `pool_size=5`, `max_overflow=10` per worker process. Accommodates up to 100 concurrent web requests across 2 ASGI workers. Introduce PgBouncer when scaling beyond 5 worker nodes.

---

## 11. First Super Admin (bootstrap)

In production, public registration **never** grants privileges
(`AUTH_BOOTSTRAP_VIA_REGISTRATION` defaults to off when `APP_ENV=production`). Create the first
Super Admin from the server, after migrations:

```bash
# Prompts for the password twice; for automation set SUPER_ADMIN_PASSWORD instead.
docker compose run --rm app python scripts/create_super_admin.py --email ops@your-domain.example --full-name "Ops"
# Or promote an existing account (ends its sessions):
docker compose run --rm app python scripts/create_super_admin.py --email someone@your-domain.example --promote
```

The Super Admin can then create Admin/User accounts in **User Administration**, and switch off
self-registration in **System Settings** if accounts should only be provisioned by administrators.

| Role | Purpose |
|---|---|
| **User** | Strictly read-only: employees (no salary/phone), dashboards, models, reports |
| **Admin** | Employee create/update (any record), delete only records they created, full ML lifecycle except deployment, manages *User* accounts, employee/ML audit log |
| **Super Admin** | Everything: roles, account deletion, employee deletion, deployments, global settings, full audit log |

---

## 12. Database migration procedure

Migrations are applied by the one-shot `migration` service (`alembic upgrade head`) before the
app starts. **Do not run production migrations without a verified backup and an approved change
window.**

1. **Back up** (Section 7) and verify the checksum.
2. **Check the current revision:** `docker compose run --rm migration alembic current`.
3. **Preview the SQL** (optional): `docker compose run --rm migration alembic upgrade head --sql`.
4. **Upgrade:** `docker compose up migration` (or `alembic upgrade head`).
5. **Verify:** `alembic current` shows `0014_drift_results_jsonb (head)`; `/api/v1/health` is `ok`;
   sign in with an existing account.

What `0012_rbac_roles` changes in existing data (reversible with `alembic downgrade 0011`):

| Old role | New role |
|---|---|
| `admin` | `super_admin` |
| `ml_engineer` | `admin` |
| `viewer` | `user` |
| anything else | `user` (fail closed) |

Existing access tokens keep working until they expire (they carry no `ver` claim, which equals
`token_version = 0`); clients see the new role on their next request because the server always
reads the role from the database.

**Databases created by the old migration lineage.** An earlier, since-deleted set of migrations
also used the IDs `0012` (`datasets.owner_id`) and `0013` (`drift_reports.results` → JSONB). A
database stamped by that lineage now fails loudly with `Can't locate revision '0013'` instead of
silently skipping the RBAC migration. Its schema equals `0011` plus those two harmless changes,
so re-stamp and upgrade:

```bash
alembic stamp --purge 0011
alembic upgrade head
```

This procedure was verified on a copy of such a database: all rows were preserved and the roles
were remapped. The leftover nullable `datasets.owner_id` column is ignored by the application.

`0014_drift_results_jsonb` fixes a pre-existing drift: fresh PostgreSQL databases had
`drift_reports.results` as `JSON` while the ORM declares `JSONB`. It converts the column only if
it is still `JSON` (a no-op otherwise) and is reversible.

---

## 13. Local LLM (Ollama) deployment

```bash
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull llama3.2:3b   # ~2 GB, once; stored in the ollama_models volume
docker compose up -d app worker                       # OLLAMA_BASE_URL defaults to http://ollama:11434
curl -s http://127.0.0.1/api/v1/health                # components.llm should be "ok"
```

- CPU only; no GPU is assumed. `llama3.2:3b` (Q4) needs about 3 GB RAM
  (`OLLAMA_MEM_LIMIT`, default 4g). A short answer takes seconds to tens of seconds on CPU.
- The service keeps one model loaded and handles one request at a time
  (`OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_QUEUE=16`); the API also bounds input/output tokens
  and rate-limits AI endpoints per client.
- Without Ollama the API still serves everything else; LLM endpoints return
  502 `provider_unavailable` and readiness reports `llm=unavailable` without failing.
- Ollama is on the internal `backend` network plus an `egress` network used only for pulling
  models. To run fully offline, pull the model once and remove the `egress` network.

---

## 14. HTTPS / TLS

The `frontend` (nginx) container listens on plain HTTP and is meant to sit behind a TLS
terminator (cloud load balancer, Caddy, Traefik, or an nginx with certificates):

1. Terminate TLS in front of `frontend` and forward to it on the private network.
2. Set `FRONTEND_PORT` to an internal port, `CORS_ORIGINS=https://your-domain`, and keep
   `FORWARDED_ALLOW_IPS` restricted to the bundled proxy (default) so rate limits see real
   client IPs.
3. Once the site is HTTPS-only, uncomment the `Strict-Transport-Security` header in
   `frontend/nginx.conf`.
4. The nginx config already sends `Content-Security-Policy`, `X-Frame-Options: DENY`,
   `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy`. The API adds its own
   security headers and `Cache-Control: no-store`.

Tokens are stored in `sessionStorage` (cleared when the tab closes) and sent as Bearer headers;
no cookies are used, so CSRF does not apply. Access tokens live 30 minutes; refresh tokens are
single-use and rotate.

---

## 15. Go-live checklist

- [ ] `JWT_SECRET_KEY` ≥ 32 random bytes, `POSTGRES_PASSWORD` strong, `.env` is `chmod 600`
- [ ] `APP_ENV=production`, `DEBUG=false`, `LOG_FORMAT=json`, explicit `CORS_ORIGINS`
- [ ] `python scripts/check_config.py --db` shows no errors
- [ ] Backup taken and restore drill done (Section 7)
- [ ] Migrations applied (Section 12); first Super Admin created (Section 11)
- [ ] TLS in front, HSTS enabled (Section 14); `DOCS_ENABLED=false` if the API is public
- [ ] `METRICS_AUTH_TOKEN` set if `/metrics` is reachable
- [ ] Optional: Ollama running and `components.llm` = `ok` (Section 13)
- [ ] Smoke test: `SMOKE_EMAIL=... SMOKE_PASSWORD=... python scripts/smoke_test.py https://your-domain --cleanup`
