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

## 6. Backup & Restore Procedures

### Database Backup:
```bash
docker compose exec -t db pg_dump -U aiproject aiproject > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Database Restore:
```bash
cat backup_*.sql | docker compose exec -T db psql -U aiproject -d aiproject
```

### Model Artifact Backup:
```bash
docker run --rm -v aiproject_models:/data -v $(pwd):/backup alpine tar czf /backup/models_backup.tar.gz /data
```

---

## 7. Graceful Shutdown & Rollback

### Stop Stack Gracefully:
```bash
docker compose down
```

### Stop and Wipe Volumes (Disaster Cleanup Only):
```bash
docker compose down -v
```

### Rollback to Previous Version:
```bash
git checkout <previous_commit_tag>
docker compose up -d --build
```
