# AIProject

A modular AI/ML platform API built with FastAPI. It provides:

- **Data:** CSV and Excel ingestion, validation and profiling, stored in PostgreSQL
  (SQLAlchemy 2.x + Alembic).
- **Classical ML:** a leakage-safe scikit-learn pipeline for training, versioned persistence and
  prediction.
- **Optional AI services:** Sentence Transformers embeddings, transformer sentiment
  classification, OpenAI chat, token counting, and a LangGraph long-text analysis workflow.
- **Operational hardening:** structured logs, request IDs, body limits, rate limiting, security
  headers, and Docker deployment files.

> **Status.** See [Verification status](#verification-status) for what has and hasn't been run.
> The project is **not** production-ready as-is. In particular it has **no authentication**; see
> [Security considerations](#security-considerations).

---

## Contents

1. [Architecture](#architecture)
2. [Project structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Local development setup](#local-development-setup)
5. [Installation options](#installation-options)
6. [PostgreSQL](#postgresql)
7. [Configuration](#configuration)
8. [Database migrations](#database-migrations)
9. [API](#api)
10. [Training → prediction workflow](#training--prediction-workflow)
11. [AI / LLM services and cost](#ai--llm-services-and-cost)
12. [Testing and quality checks](#testing-and-quality-checks)
13. [Docker](#docker)
14. [Production deployment](#production-deployment)
15. [Persistent vs runtime files](#persistent-vs-runtime-files)
16. [Security considerations](#security-considerations)
17. [Troubleshooting](#troubleshooting)
18. [Known limitations](#known-limitations)
19. [Verification status](#verification-status)

---

## Architecture

```
                 ┌──────────────────────── FastAPI app (app/main.py) ────────────────────────┐
 HTTP request ─▶ │ RequestContext → SecurityHeaders → CORS → RateLimit → BodySizeLimit → router│
                 │   (request ID, JSON access log)                (429)       (413)            │
                 │                                                                              │
                 │  api/routes ──▶ services ──▶ repositories ──▶ SQLAlchemy ──▶ PostgreSQL      │
                 │      │             │                                                         │
                 │      │             ├──▶ app/ml   (pandas, scikit-learn, joblib)  ──▶ MODEL_DIR │
                 │      │             └──▶ storage  (validated uploads)            ──▶ UPLOAD_DIR│
                 │      └──▶ app/ai container (lazy, per app)                                    │
                 │             ├── embeddings / classification ──▶ torch + HF models (optional) │
                 │             ├── LLM chat ──▶ OpenAI Responses API (optional, needs key)      │
                 │             ├── token counter (tiktoken, falls back to an estimate)          │
                 │             └── LangGraph workflow + LangChain splitter (optional)           │
                 │  core/error_handlers: every error → {"error": {code, message, details}}      │
                 └──────────────────────────────────────────────────────────────────────────────┘
```

Design principles:

- **Layers:** routes → services → repositories. The `app/ml` and `app/ai` packages don't depend
  on FastAPI, so scripts and notebooks can reuse them.
- **Optional AI:** every AI package is imported lazily. The core API starts with no AI extras and
  no API key; endpoints that need a missing piece return a 503 explaining what to install or set.
- **Safe failure:** errors use one envelope with stable codes. Internal details and secrets go
  only to the server log.

## Project structure

```
app/
  main.py              App factory create_app(); middleware order; ASGI `app`
  api/
    router.py          Registers all /api/v1 routers
    deps.py            Dependencies: settings, DB session, AI services
    routes/            root, health, datasets, models, ai
  core/
    config.py          Typed settings (env/.env), production validation
    exceptions.py      Error hierarchy with HTTP status + stable codes
    error_handlers.py  Central handlers (incl. DB errors → 503/409)
    middleware.py      Request ID/access log, security headers, body limit, rate limit
  database/            base, session (engine, diagnostics), types, models/ (Dataset, MLModel)
  repositories/        Data access
  services/            Use cases: datasets, models, storage, health
  ml/                  ingestion, validation, profiling, preprocessing, training,
                       persistence, prediction, synthetic, visualization
  ai/                  container, optional, runtime, model_cache, tokens, embeddings,
                       transformer_inference, classification, llm, text_splitting,
                       workflows/text_analysis
  schemas/             Pydantic request/response models
  utils/               logging (JSON/text + request IDs), safe paths
alembic/versions/      0001 datasets + ml_models, 0002 model versions
scripts/               check_config, check_db, smoke_test, docker_entrypoint,
                       generate_synthetic_data, profile_dataset, train_model,
                       download_models, nlp_demo, evaluate_classifier, check_health
tests/unit/            Fast tests (SQLite test double, fakes for AI)
tests/integration/     Lifecycle, migrations, optional-dependency isolation,
                       PostgreSQL (needs TEST_DATABASE_URL)
datasets/examples/     Seeded synthetic demo CSVs (committed)
Dockerfile, .dockerignore, compose.yaml, compose.dev.yaml
pyproject.toml, requirements*.txt, alembic.ini, .env.example
```

## Prerequisites

| Need | Version | Required for |
|---|---|---|
| Python | 3.12+ | everything |
| Git | any | cloning |
| PostgreSQL | 14+ (tested DDL targets 17) | dataset/model endpoints; required in production |
| Docker + Compose | Docker 24+, Compose v2.24+ | container deployment (optional for development) |
| OpenAI API key | — | `/llm/chat`, `/nlp/analyze` only |
| ~1–3 GB disk | — | only with local NLP models (PyTorch + models) |

## Local development setup

**Windows PowerShell**

```powershell
cd "C:\path\to\AIProject"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env           # then edit .env
python scripts\check_config.py
uvicorn app.main:app --reload
```

**Linux / macOS**

```bash
cd /path/to/AIProject
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env && chmod 600 .env   # then edit .env
python scripts/check_config.py
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs. Without `DATABASE_URL`, the health, AI-status and
token-count endpoints work, and the dataset/model endpoints return 503
`database_not_configured`.

## Installation options

| Group | Command | Contents | Size |
|---|---|---|---|
| Core runtime | `pip install -r requirements.txt` | FastAPI, Uvicorn, Pydantic, SQLAlchemy, psycopg, Alembic, NumPy, pandas, scikit-learn, joblib, openpyxl, Matplotlib, seaborn | ~150 MB |
| Dev & test | `pip install -r requirements-dev.txt` | core + pytest, pytest-cov, HTTPX, Ruff | small |
| LLM + workflows | `pip install -r requirements-llm.txt` (or `.[llm,agents]`) | openai (2.x/3.x), tiktoken, langgraph, langchain-core, langchain-text-splitters | ~15 MB |
| PyTorch | see below. **Install first, matching your hardware** | torch, torchvision | CPU ~200 MB; CUDA 2+ GB |
| Local NLP | `pip install -r requirements-nlp.txt` (or `.[nlp]`) | transformers (v4/v5), sentence-transformers, datasets, evaluate | + models ~360 MB |
| RAG (reserved) | `pip install -e ".[rag]"` | llama-index-core; no code uses it yet | — |

```bash
# PyTorch CPU-only (Windows/Linux):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# NVIDIA GPU: get the command for your CUDA version at https://pytorch.org/get-started/locally/
# Apple Silicon (includes MPS): pip install torch torchvision
```

Version ranges and the versions they were tested with are documented in `pyproject.toml`.

## PostgreSQL

**Option A: Docker (recommended for development).** Runs only the database in a container,
bound to `127.0.0.1:5433`:

```bash
# .env must contain POSTGRES_PASSWORD=<choose-one>
docker compose -f compose.yaml -f compose.dev.yaml up -d db
# .env: DATABASE_URL=postgresql+psycopg://aiproject:<POSTGRES_PASSWORD>@127.0.0.1:5433/aiproject
```

**Option B: a local install.** In `psql` as a superuser:

```sql
CREATE ROLE aiproject LOGIN PASSWORD '<choose-a-password>';
CREATE DATABASE aiproject OWNER aiproject;
CREATE DATABASE aiproject_test OWNER aiproject;   -- disposable, for integration tests
```

Then:

```bash
python scripts/check_db.py            # status, server version, tables; never prints the password
alembic upgrade head
python scripts/check_config.py --db   # also confirms migrations are at head
```

`postgresql://` URLs are rewritten to the psycopg 3 driver automatically. URL-encode special
characters in passwords (`@` → `%40`). Connection failures are classified as
`authentication_failed`, `database_not_found`, `connection_refused`, `host_not_found`,
`timeout` or `driver_missing`, each with a hint.

## Configuration

All settings come from environment variables, then `.env`. [.env.example](.env.example) lists
every variable with safe defaults and empty placeholders. Invalid values stop startup with a
`ConfigurationError` that lists each problem without echoing secrets.

| Area | Key variables |
|---|---|
| App | `APP_ENV` (development/testing/production), `DEBUG`, `API_V1_PREFIX`, `DOCS_ENABLED` |
| Logging | `LOG_LEVEL`, `LOG_FORMAT` (`text` / `json`) |
| HTTP hardening | `CORS_ORIGINS`, `MAX_REQUEST_BODY_MB`, `RATE_LIMIT_ENABLED`, `RATE_LIMIT_{DEFAULT,AI,TRAINING}_PER_MINUTE` |
| Database | `DATABASE_URL`, `DATABASE_CONNECT_TIMEOUT`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` |
| Storage / ML | `UPLOAD_DIR`, `MODEL_DIR`, `MAX_UPLOAD_SIZE_MB`, `MAX_DATASET_ROWS/COLUMNS`, `MAX_PREDICTION_RECORDS`, `MODEL_COMPATIBILITY_CHECK` |
| LLM | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_ALLOWED_MODELS`, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`, `LLM_MAX_*`, `LLM_LOG_CONTENT` |
| Local models | `AI_DEVICE`, `AI_MODEL_CACHE_DIR`, `AI_ALLOW_MODEL_DOWNLOADS`, `AI_INFERENCE_TIMEOUT_SECONDS`, `AI_MAX_CONCURRENT_INFERENCES`, `EMBEDDING_*`, `CLASSIFIER_*` |
| Docker Compose | `POSTGRES_USER/PASSWORD/DB`, `APP_PORT`, `INSTALL_LLM`, `INSTALL_NLP` |

**Production rules, enforced at startup:** `DATABASE_URL` must be set and must be PostgreSQL,
`DEBUG=false`, and `CORS_ORIGINS` must not contain `*`. In production CORS defaults to *no*
origins. Run `python scripts/check_config.py` for further warnings, such as docs enabled or
text logs in production.

## Database migrations

| Revision | Change |
|---|---|
| `0001` | `datasets`, `ml_models` (UUID keys, JSONB on PostgreSQL, named constraints) |
| `0002` | `ml_models.version`, unique per `name`. Existing rows are backfilled 1, 2, 3… by creation time |

```bash
alembic upgrade head          # apply
alembic downgrade -1          # roll back one revision
alembic current               # show the DB revision
alembic check                 # fails if the models and migrations differ
alembic upgrade head --sql    # print the SQL without running it
alembic revision --autogenerate -m "describe change"   # after changing models
```

In Docker, the entrypoint runs `alembic upgrade head` on start (`RUN_MIGRATIONS=true`). It
retries while the database is starting and fails fast on wrong credentials or a missing database.

## API

Interactive docs: **http://127.0.0.1:8000/docs** (Swagger), `/redoc`, and the schema at
`/openapi.json`. These are disabled when `DOCS_ENABLED=false`.

| Method & path | Purpose | Needs |
|---|---|---|
| `GET /` | Welcome | — |
| `GET /health` | Liveness (no dependencies) | — |
| `GET /api/v1/health` | Readiness incl. DB; 503 if a configured DB is down | — |
| `POST /api/v1/datasets/validate` | Validate and profile an upload **without storing it** | — |
| `POST /api/v1/datasets` | Upload and register a CSV/XLSX dataset (201) | DB |
| `GET /api/v1/datasets`, `GET /api/v1/datasets/{id}` | List / get dataset metadata | DB |
| `GET /api/v1/datasets/{id}/summary?target_column=` | Validation report and profile | DB |
| `POST /api/v1/models/train` | Train a baseline model (201); same `name` → next `version` | DB |
| `GET /api/v1/models[?dataset_id=]`, `GET /api/v1/models/{id}` | Model metadata, schema, metrics, version | DB |
| `POST /api/v1/models/{id}/predict` | Predict with a saved model | DB |
| `GET /api/v1/ai/status` | Installed AI extras, provider config (never the key), loaded models | — |
| `POST /api/v1/tokens/count` | Token count for `text` or `messages` | (`llm` for exact counts) |
| `POST /api/v1/embeddings` | Sentence embeddings with an explicit `dimension` | torch + `nlp` |
| `POST /api/v1/nlp/classify` | Sentiment classification | torch + `nlp` |
| `POST /api/v1/llm/chat` | LLM chat completion | `llm` + key |
| `POST /api/v1/nlp/analyze` | Summarise long text + sentiment (LangGraph) | `llm` + `agents` + key |

**Errors** always look like `{"error": {"code": "...", "message": "...", "details": ...}}`, and
every response carries an `X-Request-ID` header to quote in bug reports. Common codes:

| Code | Status |
|---|---|
| `validation_error`, `data_validation_error` | 422 |
| `not_found` | 404 |
| `unsupported_file_type` | 415 |
| `file_too_large`, `request_too_large` | 413 |
| `rate_limited`, `provider_rate_limited` | 429, with `Retry-After` |
| `database_not_configured`, `database_unavailable`, `optional_dependency_missing`, `provider_not_configured`, `model_load_failed` | 503 |
| `model_incompatible` | 409 |
| `provider_*` | 502 / 504 |
| `internal_server_error` | 500, generic message |

Example requests (bash; in PowerShell use `curl.exe`, or the `Invoke-RestMethod` examples in
the next section):

```bash
curl -s localhost:8000/api/v1/health
curl -s -F "file=@datasets/examples/synthetic_classification.csv" -F "target_column=label" \
  localhost:8000/api/v1/datasets/validate
curl -s -X POST localhost:8000/api/v1/tokens/count -H "Content-Type: application/json" \
  -d '{"text": "How many tokens is this?"}'
```

## Training → prediction workflow

Requires PostgreSQL with migrations applied.

**PowerShell:**
```powershell
$base = "http://127.0.0.1:8000/api/v1"
$ds = curl.exe -s -F "file=@datasets/examples/synthetic_classification.csv" -F "name=demo" "$base/datasets" | ConvertFrom-Json
$body = @{ dataset_id = $ds.dataset.id; target_column = "label"; name = "demo-model" } | ConvertTo-Json
$model = Invoke-RestMethod -Method Post -Uri "$base/models/train" -ContentType "application/json" -Body $body
"version $($model.version)"; $model.metrics.test
$records = @{ records = @(@{ num_a = 55.2; num_b = 0.7; num_c = 4; cat_a = "red"; cat_b = "small" }) } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$base/models/$($model.id)/predict" -ContentType "application/json" -Body $records
```

**bash:**
```bash
BASE=http://127.0.0.1:8000/api/v1
DS_ID=$(curl -s -F "file=@datasets/examples/synthetic_classification.csv" $BASE/datasets \
  | python -c "import sys,json; print(json.load(sys.stdin)['dataset']['id'])")
MODEL_ID=$(curl -s -X POST $BASE/models/train -H "Content-Type: application/json" \
  -d "{\"dataset_id\": \"$DS_ID\", \"target_column\": \"label\", \"name\": \"demo-model\"}" \
  | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -s -X POST $BASE/models/$MODEL_ID/predict -H "Content-Type: application/json" \
  -d '{"records": [{"num_a": 55.2, "num_b": 0.7, "num_c": 4, "cat_a": "red", "cat_b": "small"}]}'
```

Or run all of it in one go against a running server: `python scripts/smoke_test.py http://127.0.0.1:8000`.

**Training options** (`POST /models/train`):

- `target_column`, plus an optional `problem_type`. If it's omitted, text/bool targets and
  integers with ≤20 distinct values are treated as classification; everything else is regression.
- `algorithm`: `linear` (LogisticRegression / Ridge) or `random_forest`.
- `feature_columns` / `exclude_columns`: exclude IDs and anything derived from the target.
- `test_size` / `validation_size` (default 0.2 / 0.2), `random_state` (default 42),
  `drop_duplicates` (default true).

**Leakage controls:**

- The target is never used as a feature.
- Duplicate rows are dropped **before** splitting.
- All imputation, scaling and one-hot encoding are fitted on the training split only.
- Metrics are reported on validation and test, plus a `Dummy*` baseline:
  - classification: accuracy, balanced accuracy, macro P/R/F1, confusion matrix, log loss,
    ROC AUC;
  - regression: MAE, RMSE, median AE, R².

**Prediction input:** each record must contain exactly the model's `feature_schema`, and types
are checked. `null` is rejected unless `"allow_missing": true`.

**Model lifecycle:**

- Every training run creates a new artifact (`<uuid>.joblib`) and a row with `version`, the
  SHA-256 of the artifact, the scikit-learn version and full training metadata.
- Before unpickling, the hash must match, and the recorded scikit-learn **major.minor** must match
  the server's (`MODEL_COMPATIBILITY_CHECK=strict`); otherwise the API returns 409
  `model_incompatible`. A missing file returns 500 `model_artifact_error`, and an unreadable or
  wrong-format artifact returns 409.
- There's no delete endpoint yet.

Offline (no API or DB): `python scripts/train_model.py datasets/examples/synthetic_classification.csv --target label`.

## AI / LLM services and cost

- **Installed extras and status.** Check `GET /api/v1/ai/status`.
- **Missing pieces.** A missing extra gives a 503 with the exact install command; a missing key
  gives 503 `provider_not_configured`.
- **Local models.** Models are never downloaded at startup; they load lazily on first use and are
  cached (an LRU of `AI_MAX_LOADED_MODELS`), loading only once even when requests arrive
  concurrently. Pre-download them with `python scripts/download_models.py` (~360 MB), then set
  `AI_ALLOW_MODEL_DOWNLOADS=false` for offline use.
- **Devices and model safety.** `AI_DEVICE=auto` picks CUDA, then MPS, then CPU.
  `trust_remote_code` is always off. Model names come from server settings only; API requests
  can't choose a model path or repository.
- **Local NLP demo** (no key): `python scripts/nlp_demo.py`. To evaluate the classifier:
  `python scripts/evaluate_classifier.py` (uses HF `datasets` + `evaluate`).

**Controlling LLM cost:**

- `OPENAI_MODEL` (default `gpt-5.4-mini`) and the allow-list `OPENAI_ALLOWED_MODELS` decide
  which models a request may use.
- `LLM_MAX_INPUT_TOKENS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_DEFAULT_OUTPUT_TOKENS` and
  `LLM_MAX_MESSAGES` are enforced **before** any call. `RATE_LIMIT_AI_PER_MINUTE` limits how
  often each client can call.
- Every chat response includes token `usage`, and the server logs token counts per call (never
  the content), so spend can be estimated from the logs.
- `/nlp/analyze` makes one LLM call per chunk plus one to combine them: up to
  `max_chunks` (10) + 1 calls for long text.
- Reasoning models (GPT-5 family) also spend output tokens on reasoning. If `finish_reason` is
  `max_output_tokens`, raise the budget deliberately.
- Retries: the SDK retries connection errors, 429 and 5xx up to `OPENAI_MAX_RETRIES` (default 2)
  times with backoff, which can multiply cost on flaky networks. Each call times out after
  `OPENAI_TIMEOUT_SECONDS`.
- Automated tests never call paid APIs. `scripts/smoke_test.py --with-llm` makes exactly one
  short paid call.

**Privacy:** the API key is never logged or returned. Prompts and completions aren't logged
(even the SDK's DEBUG request logs are muted) unless `LLM_LOG_CONTENT=true`. Requests are sent
with `store=false`.

## Testing and quality checks

```bash
pytest                              # full suite
pytest tests/unit                   # unit only
pytest --cov=app                    # coverage
ruff check . && ruff format --check .
python -m pip check                 # dependency consistency
python scripts/check_config.py      # configuration + storage + optional extras
```

- **Database.** Unit/API tests use an in-memory SQLite database as a stand-in. The application
  itself never falls back to SQLite.
- **AI.** AI tests use deterministic fakes. OpenAI tests run the real SDK against an in-memory
  HTTP transport, so no network is used and nothing is billed.
- **Migrations.** `tests/integration/test_migrations.py` runs `0001 → 0002` with data, checks
  that migrations match the models exactly, then downgrades.
- **No AI extras.** `tests/integration/test_optional_dependencies.py` starts the app in a process
  where every AI package is blocked.

**PostgreSQL integration tests** need a **disposable** database. They run inside a transaction
that is rolled back:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://aiproject:<password>@localhost:5432/aiproject_test"; pytest -m integration
```
```bash
TEST_DATABASE_URL=postgresql+psycopg://aiproject:<password>@localhost:5432/aiproject_test pytest -m integration
```

To smoke-test a running instance end to end: `python scripts/smoke_test.py <base-url>`.

Static type checking (mypy/pyright) is **not configured** in this repository.

## Docker

```bash
cp .env.example .env               # set POSTGRES_PASSWORD; optionally OPENAI_API_KEY
docker compose up -d --build       # db + app; the app waits for db to be healthy, then migrates
docker compose ps                  # both should become "healthy"
python scripts/smoke_test.py http://127.0.0.1:8000
docker compose logs -f app         # JSON logs
docker compose down                # keeps volumes; `down -v` DELETES the database and models
```

**Image** ([Dockerfile](Dockerfile)):

- Multi-stage `python:3.12-slim` build that runs as non-root user `app` (uid 10001).
- No secrets are copied in; `.env*` is excluded by [.dockerignore](.dockerignore).
- Optional extras are build arguments: `INSTALL_LLM=true` adds OpenAI and LangGraph;
  `INSTALL_NLP=true` adds CPU PyTorch and transformers, which makes a much larger image.
- `HEALTHCHECK` probes `/health`.
- Startup goes through `scripts/docker_entrypoint.py`: validate config, migrate with retries, then
  `uvicorn --workers 2 --proxy-headers --no-access-log`.

**Compose** ([compose.yaml](compose.yaml)):

- Postgres 17 with a named volume (`pgdata`) and a `pg_isready` health check.
- The database is on an **internal network with no published port**.
- The app is published on **127.0.0.1** only, and runs with a read-only root filesystem,
  `cap_drop: ALL` and `no-new-privileges`.
- Uploads, models and the model cache are named volumes.
- `DATABASE_URL` is assembled from `POSTGRES_*`, and the stack refuses to start without
  `POSTGRES_PASSWORD`.

[compose.dev.yaml](compose.dev.yaml) runs only the database for local development, on
`127.0.0.1:5433`.

## Production deployment

Local development (above) uses `uvicorn --reload`, text logs and an optional DB. For production:

1. **Secrets.** Provide `POSTGRES_PASSWORD`, `DATABASE_URL` and `OPENAI_API_KEY` through your
   platform's secret manager, or a `chmod 600` `.env` on the host. Never put them in the image,
   the compose file or git.
2. **TLS reverse proxy.** Put Nginx, Caddy, Traefik or a cloud load balancer in front, terminating
   TLS. Keep the app bound to 127.0.0.1 or a private network. Set `--forwarded-allow-ips` (in the
   Dockerfile `CMD`) to the proxy's address so rate limiting and logs see real client IPs.
3. **Authentication.** Add it at the proxy or gateway (OAuth2/OIDC, API keys) **before exposing
   the API**. The app has none.
4. **Settings:** `APP_ENV=production`, `LOG_FORMAT=json`, explicit `CORS_ORIGINS`, and consider
   `DOCS_ENABLED=false`. Run `python scripts/check_config.py --db` inside the container.
5. **Database.** Use managed PostgreSQL or the compose service with backups (`pg_dump`, volume
   snapshots). Migrations run on start; for several replicas, run them once as a separate job
   (`RUN_MIGRATIONS=false` on the replicas).
6. **Scaling.** Rate limits and the model cache are per process. Use a gateway or Redis-based
   limiter for global limits. Size `--workers` to CPU and RAM, since each worker loads its own
   models.
7. **Monitoring.** Ship the JSON logs; alert on 5xx, `database_unavailable` and
   `provider_*` codes. Use `/health` for liveness and `/api/v1/health` for readiness.

## Persistent vs runtime files

| Path | Kind | Commit? | Notes |
|---|---|---|---|
| `app/`, `alembic/`, `scripts/`, `tests/`, config files | source | yes | |
| `datasets/examples/*.csv` | demo data | yes | regenerate with `scripts/generate_synthetic_data.py` |
| `.env.example` | template | yes | placeholders only |
| `.env`, `.env.*` | **secrets** | **never** | git- and docker-ignored |
| PostgreSQL data (`pgdata` volume / server) | **persistent state** | no | back up |
| `UPLOAD_DIR` (`uploads/`, volume `uploads`) | **persistent** user data | no | referenced by `datasets` rows |
| `MODEL_DIR` (`trained_models/`, volume `models`) | **persistent** model artifacts | no | referenced by `ml_models` rows (hash-checked) |
| `AI_MODEL_CACHE_DIR` / `~/.cache/huggingface`, tiktoken cache | re-downloadable cache | no | can be deleted |
| `reports/`, `logs/`, `*.db`, `.pytest_cache`, `.ruff_cache`, `__pycache__`, `.venv` | runtime/generated | no | safe to delete |

Back up the database **together with** `UPLOAD_DIR` and `MODEL_DIR`: the rows point to the files.

## Security considerations

**Implemented:**

- **Errors:** centralized error handling, so clients never see stack traces, SQL, file paths or
  provider messages.
- **Logging:** structured logs with request IDs. Query strings, bodies, prompts and secrets are
  not logged.
- **Input limits:** Pydantic validation with bounded sizes; a request-body limit enforced while
  streaming (413); an upload size limit.
- **Uploads:** content sniffing, zip-bomb checks, generated filenames, and path-traversal-safe
  storage.
- **Models:** joblib artifacts are loaded only from `MODEL_DIR`, by generated name, after a hash
  check and a version check. API requests can't supply paths or model locations.
- **HTTP:** restrictive CORS (none in production unless configured), security headers, and
  `Cache-Control: no-store` on API responses. Per-client rate limits, with a separate budget for
  expensive AI and training endpoints.
- **Upstream calls:** timeouts on the database and providers, and controlled retries (SDK backoff,
  migration retries).
- **Containers:** non-root, read-only filesystem, no capabilities, database not published,
  secrets supplied only at runtime.

**Not implemented. You must address these before exposing the service:**

- **Authentication and authorization.** Anyone who can reach the API can upload data, train
  models and spend LLM budget.
- **Global (cross-process) rate limiting, per-user quotas and LLM spend caps.**
- **Pickle trust.** joblib/pickle artifacts are code. Anyone with write access to `MODEL_DIR` and
  the database can execute code. Protect both.
- **Malware scanning** of uploads, data retention and deletion, and an audit trail.
- **TLS.** Must be provided by a reverse proxy.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ConfigurationError: Invalid configuration -> ...` | Fix the listed variables; run `python scripts/check_config.py` |
| 503 `database_not_configured` | Set `DATABASE_URL` and restart |
| 503 `database_unavailable` / readiness 503 | `python scripts/check_db.py` shows the category and hint |
| `relation "datasets" does not exist` / `column "version" does not exist` | `alembic upgrade head` |
| 413 `request_too_large` | Raise `MAX_REQUEST_BODY_MB` (JSON) or `MAX_UPLOAD_SIZE_MB` (files) |
| 429 `rate_limited` | Wait `Retry-After` seconds, or raise the `RATE_LIMIT_*` values |
| 409 `model_incompatible` | Retrain with the current scikit-learn version |
| 503 `optional_dependency_missing` | Run the command in `error.details.install` (PyTorch first for local models) |
| 503 `provider_not_configured` / 502 `provider_authentication_failed` | Set or replace `OPENAI_API_KEY` |
| 429 `provider_quota_exceeded` | Add billing or credits to the OpenAI account |
| `AI_DEVICE=cuda but CUDA is not available` | Install a CUDA build of PyTorch or set `AI_DEVICE=cpu` |
| First embedding/classify call is slow | It's downloading and loading the model; use `scripts/download_models.py` |
| `tokens/count` returns `approximate: true` | tiktoken is missing or offline; set `TIKTOKEN_CACHE_DIR` to a filled cache |
| Compose: `required variable POSTGRES_PASSWORD is missing` | Set it in `.env` |
| Container restarts and the entrypoint logs `authentication_failed` | The `POSTGRES_PASSWORD` changed after the volume was created; the DB keeps its original password |
| Port 8000 in use | `uvicorn app.main:app --reload --port 8001` / `APP_PORT=8001` |

## Known limitations

- **No authentication or authorization.** See [Security considerations](#security-considerations).
- **Synchronous heavy work.** Training and AI inference run in the request threadpool, with no
  job queue. A timed-out local inference keeps computing in the background.
- **Per-process state.** Rate limits and caches aren't shared between workers or replicas.
- **No delete endpoints.** Datasets and models can't be deleted through the API yet, and there's
  no model "promotion" (latest ≠ approved).
- **No streaming.** LLM responses aren't streamed.
- **No RAG yet.** LlamaIndex is only a reserved dependency group.
- **Tabular ML scope.** Datetime and free-text columns are excluded rather than engineered. There's
  no hyperparameter search.
- **No static type checking** is configured.

## Verification status

Results of the final verification run on Windows 11, Python 3.12, against this repository:

| Area | Status |
|---|---|
| pytest (unit + integration without external services) | ✅ run and passing (see the final report for counts) |
| Ruff lint + format check | ✅ passing |
| `pip check` | ✅ no broken requirements |
| App startup, `/health`, `/api/v1/health`, `/docs` | ✅ verified on a live uvicorn server |
| Upload → train → predict → versioning over HTTP | ✅ verified live with `scripts/smoke_test.py`, using **SQLite as a stand-in database** |
| Request IDs, JSON logs, security headers, 413 body limit, 429 rate limit | ✅ verified live |
| Alembic `0001`/`0002` upgrade, data backfill, `alembic check`, downgrade | ✅ verified on SQLite; PostgreSQL DDL rendered offline and reviewed |
| Startup without any AI extras or API key | ✅ verified (subprocess test + live) |
| OpenAI error mapping (401/403/429/quota/400/404/5xx/timeout/network) | ✅ real SDK with an in-memory transport (openai 2.54 and 3.40) |
| Token counting with real tiktoken | ✅ verified live |
| Docker Compose files | ✅ validated with `docker compose config` |
| **Real PostgreSQL** migrations and integration tests | ❌ **not run** (no credentials available); run them with `TEST_DATABASE_URL` |
| **Docker image build and `docker compose up`** | ❌ **not run** (Docker daemon not running) |
| **Embeddings / classification with real models** | ❌ **not run** (PyTorch and models not installed); covered by fakes only |
| **Real OpenAI calls** | ❌ **not run** (no key; tests must not make paid calls) |
| Static type checking | ➖ not configured |
