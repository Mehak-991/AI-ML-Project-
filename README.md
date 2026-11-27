# AIProject

A modular AI/ML platform API built with FastAPI. It provides:

- **Data:** CSV and Excel ingestion, validation and profiling, stored in PostgreSQL
  (SQLAlchemy 2.x + Alembic).
- **Classical ML:** a leakage-safe scikit-learn pipeline for training, versioned persistence and
  prediction.
- **Optional AI services:** Sentence Transformers embeddings, transformer sentiment
  classification, **local LLM chat through Ollama** (default `llama3.2:3b`, no API keys),
  token counting, and a LangGraph long-text analysis workflow.
- **Access control:** JWT authentication (Argon2id passwords, rotating refresh tokens) and
  backend-enforced RBAC with three roles — **User** (read-only), **Admin**, **Super Admin** —
  plus an employee directory, an audit log and global settings.
- **Operational hardening:** structured logs, request IDs, body limits, rate limiting, security
  headers, and Docker deployment files.

> **Status.** See [FINAL_AUDIT_REPORT.md](FINAL_AUDIT_REPORT.md) and [Verification status](#verification-status) for what has and hasn't been run.
> Deployment steps, the first-Super-Admin bootstrap and the migration procedure are in
> [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md). Read [Security considerations](#security-considerations)
> before exposing the service.

---

## Contents

1. [Architecture](#architecture)
2. [Project structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Quick start (setup guide)](#quick-start-setup-guide)
5. [Local development setup](#local-development-setup)
6. [Installation options](#installation-options)
7. [PostgreSQL](#postgresql)
8. [Configuration](#configuration)
9. [Database migrations](#database-migrations)
10. [API](#api)
11. [Training → prediction workflow](#training--prediction-workflow)
12. [AI / LLM services (local, via Ollama)](#ai--llm-services-local-via-ollama)
13. [Access control (RBAC)](#access-control-rbac)
14. [Testing and quality checks](#testing-and-quality-checks)
15. [Docker](#docker)
16. [Production deployment](#production-deployment)
17. [Persistent vs runtime files](#persistent-vs-runtime-files)
18. [Security considerations](#security-considerations)
19. [Troubleshooting](#troubleshooting)
20. [Known limitations](#known-limitations)
21. [Verification status](#verification-status)

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
                 │             ├── LLM chat ──▶ local Ollama server (llama3.2:3b, no key)       │
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
| Ollama + `llama3.2:3b` (~2 GB) | 0.12+ | `/llm/chat`, `/nlp/analyze` only (optional) |
| Node.js | 22 | building/testing the frontend |
| ~1–3 GB disk | — | only with local NLP models (PyTorch + models) |

## Quick start (setup guide)

The steps of the project setup guide, applied to this repository (work on the `main` branch;
the project already exists, so nothing is re-created).

**1. Virtual environment** (either name works; both are git-ignored)

```powershell
py -3.12 -m venv .venv                 # or: python -m venv venv
.\.venv\Scripts\activate               # Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
```

**2–5. Packages**, grouped in requirements files instead of one-by-one `pip install`:

| Guide step | Command | Packages |
|---|---|---|
| 2. Core + 5. FastAPI | `pip install -r requirements-dev.txt` | numpy, pandas, matplotlib, seaborn, scikit-learn, python-dotenv, openpyxl, fastapi, uvicorn, sqlalchemy, alembic, pydantic, python-multipart (+ pytest, ruff) |
| 2. Jupyter | `pip install -r requirements-notebook.txt` | notebook, jupyter, ipykernel |
| 3. Deep learning | `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu` then `pip install -r requirements-nlp.txt` | torch (CPU), transformers, sentence-transformers, datasets, evaluate |
| 4. LLM | `pip install -r requirements-llm.txt` | langchain, langgraph, llama-index-core, tiktoken |

Deliberate differences from the generic guide:
- **No `openai` package and no `OPENAI_API_KEY`.** The LLM runs locally through Ollama
  (`llama3.2:3b`): install Ollama, run `ollama pull llama3.2:3b`.
- **TensorFlow is not installed**: no code uses it and it adds ~1.5 GB. For your own
  notebooks: `pip install tensorflow-cpu`.

**6. Structure** — the guide's folders and where the code lives:

| Guide | This project |
|---|---|
| `app/api` | routers in `app/api/routes/`, dependencies in `app/api/deps.py` |
| `app/models` | ORM models (re-exported from `app/database/models/`) |
| `app/repository` | data access (re-exported from `app/repositories/`) |
| `app/services`, `app/schemas`, `app/utils`, `app/database` | as in the guide |
| `app/main.py` | FastAPI app factory; `GET /` returns the welcome message |
| `datasets/`, `notebooks/`, `uploads/`, `trained_models/`, `logs/`, `tests/` | as in the guide |
| `.env` | copy of `.env.example` (never committed) |

**8. Configuration** — `Copy-Item .env.example .env`, then set at least:

```ini
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/aimldb
JWT_SECRET_KEY=<openssl rand -hex 32>
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
```

Then create the tables: `alembic upgrade head`.

**9. Run**

```powershell
python main.py                         # or: uvicorn app.main:app --reload
```

**Testing the setup**

```powershell
python -m pip check                    # installed packages are consistent
python scripts\check_config.py --db    # settings, folders, optional packages, DB + migration revision
start http://127.0.0.1:8000/docs       # Swagger UI
curl http://127.0.0.1:8000/api/v1/health/database
jupyter notebook notebooks/01_explore_dataset.ipynb
pytest                                 # full test suite
```

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
| LLM workflows | `pip install -r requirements-llm.txt` (or `.[llm,agents]`) | tiktoken, langgraph, langchain-core, langchain-text-splitters | ~15 MB |
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
| App | `APP_ENV` (development/testing/production), `DEBUG` (verbose logs only; tracebacks are never returned to clients), `API_V1_PREFIX`, `DOCS_ENABLED` |
| Logging | `LOG_LEVEL`, `LOG_FORMAT` (`text` / `json`) |
| HTTP hardening | `CORS_ORIGINS`, `MAX_REQUEST_BODY_MB`, `RATE_LIMIT_ENABLED`, `RATE_LIMIT_{DEFAULT,AI,TRAINING,AUTH}_PER_MINUTE` |
| Auth | `JWT_SECRET_KEY` (≥ 32 bytes, required in production), `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `AUTH_BOOTSTRAP_VIA_REGISTRATION`, `METRICS_AUTH_TOKEN` |
| Database | `DATABASE_URL`, `DATABASE_CONNECT_TIMEOUT`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` |
| Storage / ML | `UPLOAD_DIR`, `MODEL_DIR`, `MAX_UPLOAD_SIZE_MB`, `MAX_DATASET_ROWS/COLUMNS`, `MAX_PREDICTION_RECORDS`, `MODEL_COMPATIBILITY_CHECK` |
| LLM (Ollama) | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_ALLOWED_MODELS`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_NUM_CTX`, `OLLAMA_NUM_THREAD`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_HEALTHCHECK_ENABLED`, `LLM_MAX_*`, `LLM_LOG_CONTENT` |
| Local models | `AI_DEVICE`, `AI_MODEL_CACHE_DIR`, `AI_ALLOW_MODEL_DOWNLOADS`, `AI_INFERENCE_TIMEOUT_SECONDS`, `AI_MAX_CONCURRENT_INFERENCES`, `EMBEDDING_*`, `CLASSIFIER_*` |
| Docker Compose | `POSTGRES_USER/PASSWORD/DB`, `APP_PORT`, `INSTALL_LLM`, `INSTALL_NLP`, `FORWARDED_ALLOW_IPS` |

**Production rules, enforced at startup:** `DATABASE_URL` must be set and must be PostgreSQL,
`DEBUG=false`, `CORS_ORIGINS` must not contain `*`, and `JWT_SECRET_KEY` must be at least 32
bytes and not the shipped default. In production CORS defaults to *no*
origins. Run `python scripts/check_config.py` for further warnings, such as docs enabled or
text logs in production.

## Database migrations

| Revision | Change |
|---|---|
| `0001` | `datasets`, `ml_models` (UUID keys, JSONB on PostgreSQL, named constraints) |
| `0002` | `ml_models.version`, unique per `name`. Existing rows are backfilled 1, 2, 3… by creation time |
| `0003`–`0011` | deployments, prediction logs, users/refresh tokens, drift, experiments, jobs, ownership, indexes |
| `0012_rbac_roles` | Three roles. Data migration `admin→super_admin`, `ml_engineer→admin`, `viewer→user` (unknown → `user`); `CHECK` constraint on `users.role`; `users.token_version`. Fully reversible |
| `0013_employees_audit` | `employees`, `audit_logs`, `system_settings` (additive) |
| `0014_drift_results_jsonb` | `drift_reports.results` JSON → JSONB on PostgreSQL when still JSON (fixes pre-existing drift; no-op otherwise) |

> A database stamped `0012`/`0013` by the **old, deleted** migration lineage (dataset owner /
> drift JSONB) must be re-stamped first: `alembic stamp --purge 0011 && alembic upgrade head`.
> Back up before migrating. See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md#database-migration-procedure).

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

## AI / LLM services (local, via Ollama)

- **No hosted provider, no API key.** Chat (`/llm/chat`) and the long-text workflow
  (`/nlp/analyze`) call a local [Ollama](https://ollama.com) server. Default model:
  `llama3.2:3b` (Q4, ~2 GB on disk, ~3 GB RAM on CPU). Install Ollama, run
  `ollama pull llama3.2:3b`, and keep `OLLAMA_BASE_URL` pointing at it.
- **Pluggable.** Routes depend on the `ChatService` protocol (`app/ai/llm.py`); add another local
  backend there and select it in `app/ai/container.py`. Other pulled models can be allowed per
  request with `OLLAMA_ALLOWED_MODELS`.
- **Failure handling.** Server down → 502 `provider_unavailable`; model not pulled → 502
  `provider_model_not_found` with the exact `ollama pull` command; slow CPU → 504
  `provider_timeout` after `OLLAMA_TIMEOUT_SECONDS`. `/api/v1/health` reports
  `components.llm` = `ok` / `model_missing` / `unavailable` but never fails readiness, because
  the rest of the API works without the LLM.
- **CPU efficiency.** `OLLAMA_NUM_CTX` (default 4096) bounds RAM and prompt time;
  `OLLAMA_NUM_THREAD` pins threads; `OLLAMA_KEEP_ALIVE` controls how long the model stays
  loaded. The compose `ollama` service keeps one model loaded and one request in flight.
- **Limits** (`LLM_MAX_INPUT_TOKENS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_MAX_MESSAGES`) are enforced
  **before** any call, and `RATE_LIMIT_AI_PER_MINUTE` throttles each client. Token counts for
  Llama models are estimates (`approximate: true`).
- **Who can use it.** LLM endpoints need the Admin or Super Admin role.
- **Local transformer models** (embeddings/classification) load lazily on first use; pre-download
  with `python scripts/download_models.py` and set `AI_ALLOW_MODEL_DOWNLOADS=false` for offline use.
- **Privacy.** Prompts and completions are never logged unless `LLM_LOG_CONTENT=true`.

## Access control (RBAC)

Every protected endpoint declares a *permission*; [app/core/permissions.py](app/core/permissions.py)
maps the three roles to permissions. The role is always read from the database row of the
authenticated user, never from the token or the request.

| Capability | User | Admin | Super Admin |
|---|:-:|:-:|:-:|
| Read employees (no salary/phone), datasets, models, monitoring, drift, settings | ✅ | ✅ | ✅ |
| See employee salary/phone | — | ✅ | ✅ |
| Create / update employees | — | ✅ | ✅ |
| Delete employees | — | — | ✅ |
| Upload, train, predict, experiments, jobs, drift analysis, LLM | — | ✅ | ✅ |
| Deploy / undeploy models | — | — | ✅ |
| List accounts; activate/deactivate/create **User** accounts | — | ✅ | ✅ |
| Change roles, manage Admin/Super Admin accounts, delete accounts | — | — | ✅ |
| Audit log | — | employee + ML events | everything |
| Change global settings (self-registration, maintenance mode, banner) | — | — | ✅ |

Additional rules: self-registration always creates a `user`; nobody can change their own role
or deactivate/delete themselves; the last active Super Admin cannot be removed; role changes,
deactivation and password changes revoke existing access *and* refresh tokens immediately
(`token_version`); maintenance mode blocks every write except a Super Admin's. Object-level
ownership still applies to models, prediction logs and jobs (Super Admins see all).

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
- **AI.** AI tests use deterministic fakes; Ollama tests use an in-memory `httpx` transport, so
  no server or model is needed.
- **RBAC.** `tests/unit/test_rbac_roles.py` exercises the permission matrix, employee CRUD,
  privilege-escalation and mass-assignment attempts, token revocation, audit logs and settings
  through the real API.
- **Migrations.** `tests/integration/test_migrations.py` runs every revision with data (including
  the role remap and its downgrade), checks that migrations match the models exactly, then
  downgrades.
- **Frontend.** `cd frontend && npm test` (Vitest + Testing Library): role-based navigation,
  route guards, per-role controls and session expiry.
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

To smoke-test a running instance end to end (admin or super admin account):
`SMOKE_EMAIL=... SMOKE_PASSWORD=... python scripts/smoke_test.py <base-url> [--with-llm] [--cleanup]`.

Static type checking (mypy/pyright) is **not configured** in this repository.

## Docker

```bash
cp .env.example .env               # set POSTGRES_PASSWORD and JWT_SECRET_KEY (openssl rand -hex 32)
docker compose up -d --build       # db + migration + app + worker + frontend
docker compose --profile llm up -d # optional: local Ollama; then
docker compose exec ollama ollama pull llama3.2:3b
docker compose run --rm app python scripts/create_super_admin.py --email you@example.com
docker compose ps                  # both should become "healthy"
python scripts/smoke_test.py http://127.0.0.1:8000
docker compose logs -f app         # JSON logs
docker compose down                # keeps volumes; `down -v` DELETES the database and models
```

**Image** ([Dockerfile](Dockerfile)):

- Multi-stage `python:3.12-slim` build that runs as non-root user `app` (uid 10001).
- No secrets are copied in; `.env*` is excluded by [.dockerignore](.dockerignore).
- Optional extras are build arguments: `INSTALL_LLM=true` adds the LangGraph/tiktoken workflow extras;
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

Follow [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md). In short:

1. **Secrets** (`POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, optional `METRICS_AUTH_TOKEN`) come from a
   secret manager or a `chmod 600` `.env`; never from the image or git. No API keys are needed.
2. **TLS** is terminated by a reverse proxy or load balancer in front of the `frontend` container;
   set `FORWARDED_ALLOW_IPS` to it and enable HSTS in `frontend/nginx.conf` once HTTPS-only.
3. **First Super Admin:** `python scripts/create_super_admin.py --email ...` (public registration
   never grants privileges in production).
4. **Back up, then migrate** (`alembic upgrade head`, run once by the `migration` service).
5. **Settings:** `APP_ENV=production`, `LOG_FORMAT=json`, explicit `CORS_ORIGINS`, consider
   `DOCS_ENABLED=false`; then `python scripts/check_config.py --db`.
6. **Monitoring:** `/health` (liveness), `/api/v1/health` (readiness), `/api/v1/health/database`,
   `/metrics` (protect with `METRICS_AUTH_TOKEN`), JSON logs, and the audit log.

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
- **Uploads:** content sniffing, zip-bomb checks, XML hardening for `.xlsx` (defusedxml), generated
  filenames, and path-traversal-safe storage.
- **Models:** joblib artifacts are loaded only from `MODEL_DIR`, by generated name, after a hash
  check and a version check. API requests can't supply paths or model locations.
- **HTTP:** restrictive CORS (none in production unless configured), security headers, and
  `Cache-Control: no-store` on API responses. Per-client rate limits, with a separate budget for
  expensive AI and training endpoints.
- **Upstream calls:** timeouts on the database and providers, and controlled retries (SDK backoff,
  migration retries).
- **Containers:** non-root, read-only filesystem, no capabilities, database not published,
  secrets supplied only at runtime.

- **Authentication & RBAC:** JWT access tokens (HS256, 30 min) with rotating single-use refresh
  tokens; Argon2id password hashing (legacy PBKDF2/bcrypt hashes upgraded at login);
  timing-equalised logins; backend permission checks on every endpoint; token revocation on
  password/role change and deactivation; strict request schemas (`extra="forbid"`) against mass
  assignment; `CHECK` constraint on roles; audit log of sensitive operations.

**Not implemented. Address these as needed:**

- **Global (cross-process) rate limiting and per-user quotas.** Limits are per process.
- **MFA, account lockout and password-reset e-mail.** Login is rate limited, not locked out.
- **Pickle trust.** joblib/pickle artifacts are code. Anyone with write access to `MODEL_DIR` and
  the database can execute code. Protect both.
- **Malware scanning** of uploads, and dataset/model deletion through the API.
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
| 502 `provider_unavailable` on `/llm/chat` | Start Ollama (`ollama serve`) and check `OLLAMA_BASE_URL` |
| 502 `provider_model_not_found` | `ollama pull llama3.2:3b` (or the configured `OLLAMA_MODEL`) |
| 504 `provider_timeout` | CPU too slow for the request: lower `max_output_tokens`/`OLLAMA_NUM_CTX` or raise `OLLAMA_TIMEOUT_SECONDS` |
| 403 `permission_denied` | The role lacks the permission named in `error.details.required_permission` |
| 401 "Session is no longer valid" | Password or role changed, or account deactivated: sign in again |
| 503 `maintenance_mode` | A Super Admin enabled maintenance mode in System Settings |
| Alembic `Can't locate revision '0013'` | DB stamped by the old lineage: `alembic stamp --purge 0011 && alembic upgrade head` |
| `AI_DEVICE=cuda but CUDA is not available` | Install a CUDA build of PyTorch or set `AI_DEVICE=cpu` |
| First embedding/classify call is slow | It's downloading and loading the model; use `scripts/download_models.py` |
| `tokens/count` returns `approximate: true` | tiktoken is missing or offline; set `TIKTOKEN_CACHE_DIR` to a filled cache |
| Compose: `required variable POSTGRES_PASSWORD is missing` | Set it in `.env` |
| Container restarts and the entrypoint logs `authentication_failed` | The `POSTGRES_PASSWORD` changed after the volume was created; the DB keeps its original password |
| Port 8000 in use | `uvicorn app.main:app --reload --port 8001` / `APP_PORT=8001` |

## Known limitations

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

Final verification run (Windows 11, Python 3.12, PostgreSQL 18, Ollama with `llama3.2:3b`):

| Area | Status |
|---|---|
| Backend pytest (unit + integration without external services) | ✅ passing |
| PostgreSQL: full migration chain on an empty DB; schema identical to the ORM | ✅ run |
| PostgreSQL: role-remap migration on a **copy** of a real dev DB, data preserved, downgrade/upgrade round trip | ✅ run |
| PostgreSQL integration tests (`TEST_DATABASE_URL`) | ⚠️ 10/11 pass; `test_api_workflow_against_postgres` fails in its test harness (pre-existing, also fails on the original commit) |
| Live production-mode server on PostgreSQL: smoke test incl. login, upload → train → predict, employee CRUD, audit log | ✅ verified |
| Live RBAC checks per role over HTTP on PostgreSQL | ✅ verified |
| Real Ollama chat call (`llama3.2:3b`, CPU) | ✅ verified |
| Frontend: `tsc` + production build, Vitest RBAC tests | ✅ passing |
| Docker Compose files | ✅ validated with `docker compose config` (with and without the `llm` profile) |
| **Docker image build and `docker compose up`** | ❌ not run (Docker daemon not running) |
| **Embeddings / classification with real models** | ❌ not run (PyTorch not installed); covered by fakes |
| Static type checking (Python) | ➖ not configured |

