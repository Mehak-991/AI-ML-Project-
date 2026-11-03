# Deployment Guide

How to deploy AIProject v0.4.0 with Docker Compose on one host, and how to run it afterwards. For
variables see [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md).

> **Never run `docker compose down -v`.** It deletes the database, uploaded datasets and trained
> models. Plain `docker compose down` keeps them.

## Architecture

```
 Browser ──TLS──▶ your TLS terminator ──▶ frontend (Nginx :80)
                                            ├─ /            React SPA
                                            └─ /api/  ─────▶ app (FastAPI, 2 uvicorn processes)
                                                               │        │
                  backend network (internal, no host access)   ▼        ▼
                                                              db     volumes: uploads,
                                                       (PostgreSQL)  trained_models, model_cache
                                                               ▲        ▲
                                                             worker ────┘  claims jobs from db
                  migration: runs `alembic upgrade head` once, then exits
```

| Service | Role | Health check | Restart |
|---|---|---|---|
| `db` | PostgreSQL 18, volume `pgdata` | `pg_isready` | unless-stopped |
| `migration` | Applies migrations before `app` and `worker` start | exit code 0 | no |
| `app` | API; port not published | `GET /health` | unless-stopped |
| `worker` | Runs background jobs and recovers stalled ones, 3 at a time | heartbeat file age | unless-stopped |
| `frontend` | SPA and reverse proxy; only published port | `GET /healthz` | unless-stopped |

## Prerequisites

- Docker Engine 24+ and Compose v2.20+
- 4 GB RAM or more: `app` and `worker` are limited to 2 GB each, `db` to 1 GB
- A TLS terminator (Caddy, Traefik, a load balancer) and a domain name for real deployments

## First deployment

```bash
cp .env.production.example .env.production
chmod 600 .env.production
# Set POSTGRES_PASSWORD and JWT_SECRET_KEY; openssl rand -hex 32 generates a value.

docker compose --env-file .env.production config --quiet       # validates; prints nothing if OK
docker compose --env-file .env.production up -d --build --wait # waits until all are healthy
docker compose --env-file .env.production ps
curl -s http://localhost/api/v1/health                         # {"status":"ok",...}
```

Without `POSTGRES_PASSWORD` or `JWT_SECRET_KEY`, or with a weak JWT secret, the stack refuses to
start and says why.

**Then immediately create your admin:** the first account registered on an empty database becomes
admin. Open the site and register, before anyone else can reach it.

### Existing project volumes

The Compose project is named `aiproject`, so volumes are `aiproject_pgdata` and so on. Starting this
version against existing volumes keeps the data and applies the additive migrations `0012` and
`0013`. Take a backup first (see below).

## TLS

Nginx serves plain HTTP. Terminate TLS in front of it, for example with Caddy on the same host:

```
your-domain.example {
    reverse_proxy 127.0.0.1:8080
}
```

Set `FRONTEND_PORT=8080`, and publish only 127.0.0.1 by changing the `ports` entry to
`"127.0.0.1:${FRONTEND_PORT:-80}:80"`, so nothing bypasses TLS.

**Required behind any terminator:** rate limits and logs use the client IP as seen by Nginx, which
would now be the terminator's, so all users would share one budget. Tell Nginx to trust it by adding
this to the `server` block in `frontend/nginx.conf`, with the address your terminator connects from:

```nginx
set_real_ip_from 172.16.0.0/12;   # the Docker gateway, for a terminator on the same host
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

Then check that `client_ip` in `docker compose logs app` shows real addresses. This setup depends on
your terminator, so it has not been tested as part of this project's verification.

## Updating

```bash
python scripts/backup_db.py --retention 7                       # backup first
git pull
APP_VERSION=0.4.1 docker compose --env-file .env.production up -d --build --wait
curl -s http://localhost/api/v1/health
```

Set `APP_VERSION` per release so the previous image stays available for rollback. Migrations run
automatically through the `migration` service.

## Rollback

```bash
APP_VERSION=0.4.0 docker compose --env-file .env.production up -d --no-build --wait
curl -s http://localhost/api/v1/health
```

Volumes are untouched. Older images run fine against the newer schema when the migrations in between
are additive, as `0012` and `0013` are. If a release includes a non-additive migration, restore the
pre-update backup into a new database rather than downgrading in place.

## Health checks

| Check | Command | Meaning |
|---|---|---|
| Containers | `docker compose ps` | All healthy; `migration` exited (0) |
| Readiness | `curl http://localhost/api/v1/health` | 200 when the database answers, else 503 |
| Nginx | `curl http://localhost/healthz` | Proxy is up |
| API liveness | `docker compose exec app python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/health').read())"` | Process is up; ignores dependencies |
| Worker | `docker compose exec worker python scripts/check_worker_health.py` | Heartbeat under 30 s old |
| Configuration | `docker compose exec app python scripts/check_config.py --db` | Settings, storage, migration revision |

`curl http://localhost/health` returns the SPA, not the API: Nginx only proxies `/api/`.

## Monitoring

Logs are JSON, one object per line: `docker compose logs -f app worker`. Quote the `X-Request-ID`
response header to find a request. Alert on HTTP 5xx, `database_unavailable`, and
`Stalled-job recovery` messages.

`GET /metrics` on `app:8000` serves Prometheus metrics. Nginx deliberately doesn't expose it, so run
Prometheus on the `aiproject_backend` network, and set `METRICS_TOKEN` to require a bearer token:

```yaml
scrape_configs:
  - job_name: aiproject
    static_configs: [{ targets: ["app:8000"] }]
    authorization: { credentials_file: /etc/prometheus/metrics_token }
```

| Metric | Meaning |
|---|---|
| `aiml_models_total` | Registered models |
| `aiml_jobs_by_status{status}` | Jobs per state. Watch `failed` and a growing `queued` |
| `aiml_predictions_total{status}` | Prediction requests |
| `aiml_prediction_records_total{status}` | Records predicted |
| `aiml_prediction_duration_ms_avg{status}` | All-time average, so a poor signal of recent changes |
| `aiml_worker_health_status` | 1 when the worker's heartbeat is fresh. Alert on 0 |

Metrics are computed from the database on each scrape; no HTTP request histograms exist. The bundled
stack doesn't include Prometheus or Grafana.

## Backup and restore

`scripts/backup_db.py` runs `pg_dump` through `docker exec`, then writes a gzip file, a SHA-256 file
and metadata. Dumps contain user emails and password hashes: **keep them out of git**, and copy them
off the host.

```bash
python scripts/backup_db.py --retention 7 --output-dir backups
python scripts/backup_db.py --remote-sync "aws s3 cp {file} s3://your-bucket/"   # optional off-host copy
python scripts/restore_db.py --backup backups/<file>.sql.gz --verify-only        # checksum only
```

Test a restore regularly, into a **separate** database; it stops at the first SQL error:

```bash
python scripts/restore_db.py --backup backups/<file>.sql.gz --target-db aiproject_restore_test --confirm
docker compose exec db psql -U aiproject -d aiproject_restore_test -c "SELECT count(*) FROM users;"
docker compose exec db psql -U aiproject -d postgres -c "DROP DATABASE aiproject_restore_test;"
```

Datasets and model files are not in the database dump. Back up those volumes too:

```bash
docker run --rm -v aiproject_uploads:/from:ro -v "$PWD/backups:/to" alpine tar czf /to/uploads.tar.gz -C /from .
docker run --rm -v aiproject_models:/from:ro -v "$PWD/backups:/to" alpine tar czf /to/models.tar.gz -C /from .
```

Restoring over the live database replaces its contents. To do that deliberately: stop `app` and
`worker`, take a fresh backup, restore with `--target-db aiproject --confirm`, then start them again.

## Background jobs

- `app` queues jobs in PostgreSQL; `worker` claims them with `FOR UPDATE SKIP LOCKED`, so one worker
  or several never run the same job twice.
- A job that stops heartbeating (worker crash, OOM) is re-queued after
  `JOB_STALE_TIMEOUT_MINUTES` (default 15), or marked `failed` once retries run out.
- Client errors (bad data, missing objects) fail immediately without retries.
- Cancelling a running job doesn't interrupt the computation: its result is discarded.
- Scale with `docker compose up -d --scale worker=2`, within available memory. Workers share one
  heartbeat file, so the health check and metric can't tell a dead worker from a live one then.

## Local LLM with Ollama

Install Ollama on the Docker host and pull the model, then set `LLM_PROVIDER=ollama`. Containers reach
the host through `host.docker.internal`, which `compose.yaml` configures. On Linux, make Ollama listen
beyond loopback (`OLLAMA_HOST=0.0.0.0`) and firewall port 11434 from the internet. LLM calls run in
the request and can be slow on CPU; Nginx allows 300 s.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `required variable JWT_SECRET_KEY is missing` | Pass `--env-file .env.production` on every compose command |
| Containers exit with `JWT_SECRET_KEY must be set` | Secret is the public default or under 32 bytes |
| `migration` exits non-zero | `docker compose logs migration`. `authentication_failed` means `POSTGRES_PASSWORD` changed after the volume was created; the database keeps its original password |
| 502 from `/api/` | `app` is down or starting: `docker compose logs app` |
| 429 for everyone at once | Clients aren't being told apart; check `client_ip` in the logs, and see TLS above |
| Jobs stay `queued` | Worker down: `docker compose ps worker`, `docker compose logs worker` |
| Jobs stay `running` after a crash | Normal until `JOB_STALE_TIMEOUT_MINUTES` passes |
| `model_incompatible` (409) | Model trained on another scikit-learn minor version: retrain. `requirements.lock` keeps builds stable |
| LLM returns 502/503 | Ollama not running or the model isn't pulled |
| `address already in use` on port 80 | Another stack holds it: set `FRONTEND_PORT` |
| Network overlap error | Change `FRONTEND_SUBNET` and `FRONTEND_PROXY_IP` together |
