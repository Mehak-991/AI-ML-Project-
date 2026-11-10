# Environment Setup

How configuration is split between local development and production, and every variable you may need
to set. Defaults live in [app/core/config.py](app/core/config.py).

## Which file is used where

| Context | File | Template | Notes |
|---|---|---|---|
| Local development (uvicorn on the host) | `.env` | [.env.example](.env.example) | Read by the application |
| Docker Compose production | `.env.production` | [.env.production.example](.env.production.example) | Passed with `--env-file`; `ENV_FILE` tells containers to load it too |

Both are ignored by git and excluded from Docker images. Never commit them.

`compose.yaml` always forces `APP_ENV=production`, `DEBUG=false`, `DATABASE_ECHO=false`,
`LOG_FORMAT=json`, the database URL, storage paths and proxy trust, so a development `.env` can't
weaken a Compose deployment.

## Local development (Windows)

Needs Python 3.12, Node.js 22 and PostgreSQL 18.

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -c requirements.lock -r requirements-dev.txt
Copy-Item .env.example .env        # then set DATABASE_URL
.\.venv312\Scripts\python.exe -m alembic upgrade head
.\.venv312\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second terminal, only if you want `retry_pending` jobs and stalled-job recovery locally
(`JOB_INLINE_DISPATCH=true` already runs new jobs inside the API):

```powershell
$env:WORKER_HEARTBEAT_FILE = "$PWD\logs\worker_heartbeat"
.\.venv312\Scripts\python.exe scripts\run_worker.py
```

Frontend, in a third terminal (serves http://localhost:3000 and proxies `/api` to `http://127.0.0.1:8000`
by default, which is the API from the step above):

```powershell
cd frontend
npm ci
npm run dev
```

**Develop against the Docker stack instead** (no extra port is published on the API container): point
the dev proxy at the stack's nginx origin with `VITE_DEV_API_TARGET`. It must be an `http(s)` origin;
anything else stops the dev server at startup with a clear error.

```powershell
cd frontend
$env:VITE_DEV_API_TARGET = "http://localhost"; npm run dev
# or keep it in frontend\.env.local (git-ignored):  VITE_DEV_API_TARGET=http://localhost
```

Check the setup with `.\.venv312\Scripts\python.exe scripts\check_config.py --db`.

**`502 Bad Gateway` on `/api/...` at port 3000** means the Vite proxy found nothing at its target. The
development page then says "The API server is not running" and names the target it tried. The
frontend doesn't start the API: start it as above, or point the proxy at a running stack with
`VITE_DEV_API_TARGET`. That message exists only in `npm run dev`; the Docker stack at
`http://localhost/` never shows it. Check a stack or dev server with
`python scripts\check_stack.py --origin http://localhost` (or `http://localhost:3000`).

## Required in production

Startup fails without these.

| Variable | Purpose | Generate with |
|---|---|---|
| `POSTGRES_PASSWORD` | Database password. Set once: the database keeps its original password if you change this later | `openssl rand -hex 24` |
| `JWT_SECRET_KEY` | Signs access tokens; at least 32 bytes, and not the public default. Changing it signs everyone out | `openssl rand -hex 32` |

Outside Compose you must also set `DATABASE_URL` (PostgreSQL only) and `APP_ENV=production`.

## Common settings

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_DB` | `aiproject` | Database identity, Compose only |
| `APP_VERSION` | **required, no default** | Release tag of the images (production: `0.5.0-p21`). Compose and `scripts/preflight.py` refuse a missing value, `latest` and the retired `0.4.0`. Also reported as `release` by `/health` |
| `FRONTEND_PORT` | `80` | Host port for Nginx |
| `FRONTEND_SUBNET`, `FRONTEND_PROXY_IP` | `172.21.0.0/16`, `172.21.0.10` | Change together if the subnet clashes with another network |
| `CORS_ORIGINS` | none in production | Comma-separated. Leave empty when served through the bundled Nginx |
| `PROD_DOCS_ENABLED` | `false` | Serve Swagger UI and the schema in Compose |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `METRICS_TOKEN` | unset | When set, `/metrics` requires this bearer token. Set it before enabling Prometheus ([MONITORING.md](MONITORING.md)); preflight warns while unset |
| `PASSWORD_REHASH_ON_LOGIN` | `true` | Upgrade old PBKDF2/bcrypt hashes to Argon2id after a successful login. Set `false` for the first rollout of a release with Argon2id so a rollback to an older image cannot lock upgraded accounts out; set it back to `true` once you are committed to the release |
| `ALLOW_FIRST_USER_ADMIN` | `false` | Local development only: the first public registration becomes admin. **Refused when `APP_ENV=production`.** Production creates its first admin with `scripts/create_admin.py` |
| `BOOTSTRAP_ADMIN_PASSWORD` | unset | Read only by `scripts/create_admin.py` for a non-interactive bootstrap; never stored by the app. Unset it afterwards |
| `TLS_CERT_DIR`, `FRONTEND_TLS_PORT` | none, `443` | Only with `compose.tls.yaml`: folder holding `fullchain.pem` and `privkey.pem` ([TLS_DEPLOYMENT.md](TLS_DEPLOYMENT.md)) |
| `PROMETHEUS_BIND`, `PROMETHEUS_PORT` | `127.0.0.1`, `9090` | Only with `compose.monitoring.yaml` |

## Limits

| Variable | Default | Purpose |
|---|---|---|
| `MAX_UPLOAD_SIZE_MB` | `25` | Keep below Nginx's `client_max_body_size` (50 MB) |
| `MAX_REQUEST_BODY_MB` | `5` | JSON bodies |
| `MAX_DATASET_ROWS`, `MAX_DATASET_COLUMNS` | `200000`, `500` | Rejected above these |
| `MAX_PREDICTION_RECORDS` | `1000` | Per prediction request or batch job |
| `RATE_LIMIT_ENABLED` | `true` | Keep on unless a gateway limits instead |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | `300` | Per client IP, per process |
| `RATE_LIMIT_TRAINING_PER_MINUTE` | `10` | Uploads, training, experiment runs |
| `RATE_LIMIT_ANALYSIS_PER_MINUTE` | `60` | Job submission, SHAP/LIME, drift analysis |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `20` | Login, register, refresh, change password |
| `RATE_LIMIT_AI_PER_MINUTE` | `30` | LLM, NLP, embeddings |

## Background jobs

| Variable | Default | Purpose |
|---|---|---|
| `JOB_INLINE_DISPATCH` | `true`; Compose API `false` | Whether the API also runs jobs itself |
| `JOB_STALE_TIMEOUT_MINUTES` | `15` | A running job without a heartbeat for this long is recovered |
| `JOB_STALE_TIMEOUT_BY_TYPE` | `{}` | JSON overrides per job type |
| `JOB_HEARTBEAT_INTERVAL_SECONDS` | `30` | Stale timeouts must be at least 3× this |
| `JOB_REAPER_INTERVAL_SECONDS` | `60` | How often the worker looks for stalled jobs |
| `WORKER_HEARTBEAT_FILE` | `/tmp/worker_heartbeat`; Compose uses the shared volume | Read by the healthcheck and `/metrics` |

## Database

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | `5`, `10` | Per process. Compose runs 2 API processes plus the worker: keep the total below PostgreSQL's `max_connections` |
| `DATABASE_CONNECT_TIMEOUT` | `5` | Seconds |
| `TEST_DATABASE_URL` | unset | Integration tests only. Must point at a **disposable** database |

## LLM (optional)

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `ollama` (local, free) or `openai` (hosted, paid) |
| `OLLAMA_MODEL` | `llama3.2:3b` | Run `ollama pull <model>` first |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Host development |
| `DOCKER_OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | From containers; must be reachable from them |
| `OLLAMA_TIMEOUT_SECONDS` | `180` | Stay under Nginx's 300 s |
| `OPENAI_API_KEY` | unset | Without it, OpenAI endpoints return 503 |
| `INSTALL_LLM`, `INSTALL_NLP` | `false` | Build arguments for optional packages |

The remaining `AI_*`, `EMBEDDING_*`, `CLASSIFIER_*`, `LLM_*` and `TOKENIZER_*` settings are described
in [.env.example](.env.example).

## Frontend build

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | Only for an API on a different origin; also set `CORS_ORIGINS` |
| `VITE_SHOW_API_DOCS` | off in production builds | Shows the API docs links; pair with `PROD_DOCS_ENABLED=true` |
| `VITE_DEV_API_TARGET` | `http://127.0.0.1:8000` | **`npm run dev` only:** where the dev server proxies `/api`. Never compiled into a production build (the bundle is checked for it) |

These are compiled in at build time, so they are public. Never put secrets in `VITE_*` variables.

## Validate a configuration

```bash
python scripts/check_config.py --db                              # local
docker compose --env-file .env.production exec app python scripts/check_config.py --db
docker compose --env-file .env.production config --quiet         # compose interpolation
```

These print no secret values.
