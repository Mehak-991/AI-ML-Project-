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
# APP_VERSION is already set to the release tag (0.5.0-p21); it has no default on purpose.

python scripts/preflight.py --env-file .env.production --check-docker   # refuses an unsafe release
docker compose --env-file .env.production config --quiet       # validates; prints nothing if OK
docker compose --env-file .env.production up -d --build --wait # waits until all are healthy
docker compose --env-file .env.production ps
curl -s http://localhost/api/v1/health                         # {"status":"ok","release":"0.5.0-p21",...}
```

Without `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` or `APP_VERSION`, or with a weak JWT secret, the stack
refuses to start and says why. Compose also refuses any command (even `ps`) when `APP_VERSION` is
unset; that is intentional, so a forgotten tag can never fall back to an old or moving image.
`scripts/preflight.py` additionally rejects `latest` and the retired `0.4.0`.

**Then create your admin explicitly.** Registering through the site never makes anyone an admin on
a fresh database: every public registration is a `viewer`. Create the first administrator from the
server, once:

```powershell
# interactive: prompts for the password twice, nothing is echoed
docker compose --env-file .env.production run --rm --no-deps -it app python scripts/create_admin.py --email you@example.com

# non-interactive: the password comes from the environment, never from the command line
$env:BOOTSTRAP_ADMIN_PASSWORD = "<your password>"
docker compose --env-file .env.production run --rm --no-deps -e BOOTSTRAP_ADMIN_PASSWORD app python scripts/create_admin.py --email you@example.com
Remove-Item Env:BOOTSTRAP_ADMIN_PASSWORD
```

It is one-time: it refuses when an active administrator already exists, and it never promotes or
changes an existing account. More admins are made by an existing admin under User Administration.
(`ALLOW_FIRST_USER_ADMIN=true` restores "first registration is admin" for local development only;
production refuses to start with it.)

### Existing project volumes

The Compose project is named `aiproject`, so volumes are `aiproject_pgdata` and so on. Starting this
version against existing volumes keeps the data and applies the additive migrations `0012` and
`0013`. Take a backup first (see below).

## TLS

The bundled Nginx serves plain HTTP by default, so local development is unchanged. For a real
deployment choose one of two opt-in setups; both are described, with the exact commands, in
[TLS_DEPLOYMENT.md](TLS_DEPLOYMENT.md):

- **Nginx terminates TLS** (`compose.tls.yaml`): you supply `fullchain.pem` and `privkey.pem`. Port 80
  redirects to HTTPS, HSTS is sent, and the API is told the request was HTTPS.
- **A load balancer or proxy (Caddy, Traefik, cloud LB) terminates TLS in front of Nginx:** list the
  proxy's address in `frontend/proxy-trust.conf`. Nginx then believes its `X-Forwarded-Proto` and
  client IP, and ignores them from anyone else.

No certificate ships with the project and none is created for you. Never expose port 80 of the plain
HTTP setup directly to the internet.

## Updating

```bash
python scripts/backup_db.py --retention 7                       # backup first
git pull
# Edit APP_VERSION in .env.production to the new release tag (e.g. 0.5.0-p22), then:
python scripts/preflight.py --env-file .env.production --check-docker
docker compose --env-file .env.production up -d --build --wait
curl -s http://localhost/api/v1/health                          # "release" shows the live tag
```

Use a new, never-reused `APP_VERSION` per release so the previous image stays available for
rollback. Migrations run automatically through the `migration` service. Changing the tag recreates
`app`, `worker` and `frontend` (a short interruption); the database container and all volumes are
left alone.

## Rollback

```bash
# Set APP_VERSION in .env.production back to the previous tag (the pre-p21 images are tagged
# pre-p21), then:
docker compose --env-file .env.production up -d --no-build --wait
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

`GET /metrics` on `app:8000` serves Prometheus metrics. Nginx deliberately answers 404 for it on the
public entry point. `compose.monitoring.yaml` adds an opt-in Prometheus that scrapes it over the
internal network with a bearer token (`METRICS_TOKEN`); setup and verification are in
[MONITORING.md](MONITORING.md).

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
