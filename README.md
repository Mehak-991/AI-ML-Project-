# AIProject — AI/ML Platform with Role-Based Access Control

A full-stack AI/ML platform: a **FastAPI** backend with **PostgreSQL**, a **React** frontend, a
scikit-learn training and prediction pipeline, local LLM chat through **Ollama** (no API keys),
and backend-enforced **role-based access control** with three roles: **User**, **Admin** and
**Super Admin**.

| | |
|---|---|
| **Live app** | https://aiml-project-ecru.vercel.app |
| **Backend API** | https://aiml-backend-yrj8.onrender.com |
| **API docs (Swagger)** | https://aiml-backend-yrj8.onrender.com/docs |

> The live backend runs on Render's free plan: it sleeps after ~15 minutes without traffic, so
> the first request can take about a minute. LLM chat is disabled online (see
> [AI / LLM](#ai--llm-ollama)).

---

## Contents

1. [Features](#features)
2. [Roles and permissions](#roles-and-permissions)
3. [Tech stack](#tech-stack)
4. [Architecture](#architecture)
5. [Project structure](#project-structure)
6. [Quick start (local)](#quick-start-local)
7. [Configuration](#configuration)
8. [Database and migrations](#database-and-migrations)
9. [API overview](#api-overview)
10. [Training → prediction workflow](#training--prediction-workflow)
11. [AI / LLM (Ollama)](#ai--llm-ollama)
12. [Frontend](#frontend)
13. [Testing](#testing)
14. [Deployment](#deployment)
15. [Security](#security)
16. [Troubleshooting](#troubleshooting)
17. [Known limitations](#known-limitations)
18. [Verification status](#verification-status)

---

## Features

- **Authentication:** email + password sign-in, JWT access tokens (30 min) with rotating
  single-use refresh tokens, Argon2id password hashing, sessions revoked on password or role
  change.
- **Three roles enforced by the backend** on every endpoint (details below), including one-time
  sign-up for the Admin and Super Admin accounts.
- **Employee directory:** create, edit, search, filter and paginate employee records; salary and
  phone are hidden from read-only users; Admins delete only the records they created.
- **Audit log** of sensitive actions (logins, account and role changes, employee changes, dataset
  uploads, training, deployments, settings changes).
- **Global settings** (Super Admin): open/close public sign-up, maintenance mode, announcement
  banner.
- **Datasets:** CSV/Excel upload with validation and profiling.
- **Classical ML:** leakage-safe scikit-learn training (classification and regression), model
  versioning, predictions, experiments, background jobs.
- **MLOps:** deployments, monitoring, data-drift and data-quality reports, explainability
  (SHAP/LIME), prediction history with ground-truth feedback.
- **Local AI:** LLM chat and text analysis via Ollama (`llama3.2:3b`); optional embeddings and
  sentiment classification with local transformer models.
- **Production hardening:** structured JSON logs with request IDs, rate limiting, request-size
  limits, security headers, health checks, Docker images, database backup/restore scripts.

## Roles and permissions

The role is always read from the database, never from the token or the request, so it can't be
faked from the browser. All rules are defined in [app/core/permissions.py](app/core/permissions.py).

| Capability | User | Admin | Super Admin |
|---|:-:|:-:|:-:|
| View employees (without salary/phone), datasets, models, reports, dashboards | ✅ | ✅ | ✅ |
| View employee salary and phone | — | ✅ | ✅ |
| Create and edit employees | — | ✅ any record | ✅ any record |
| Delete employees | — | ✅ only records they created | ✅ any record |
| Upload datasets, train models, predict, experiments, jobs, LLM chat | — | ✅ | ✅ |
| Deploy / undeploy models | — | — | ✅ |
| User Administration | — | list; manage **User** accounts | everything |
| Change roles, delete accounts | — | — | ✅ |
| Audit log | — | employee + ML events | everything |
| Change global settings | — | — | ✅ |

**Account rules**

- **Sign-up:** anyone can create any number of **User** accounts. An **Admin** or **Super
  Admin** account can be created through sign-up **only once per role**: the first such account
  permanently closes that option (deactivating, demoting or deleting it does not reopen it).
  After that, only a Super Admin can grant those roles.
- Nobody can change their own role or deactivate/delete their own account.
- The last active Super Admin cannot be removed.
- Changing a password or role, or deactivating an account, ends that account's existing sessions
  immediately.
- **Maintenance mode** blocks every change except a Super Admin's.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL (16+), SQLAlchemy 2, Alembic migrations, psycopg 3 |
| Auth | PyJWT, Argon2id (argon2-cffi) |
| ML / data | NumPy, pandas, scikit-learn, joblib, Matplotlib, seaborn, SHAP, LIME |
| AI (optional) | Ollama (`llama3.2:3b`), PyTorch (CPU), transformers, sentence-transformers, LangChain, LangGraph, LlamaIndex, tiktoken |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, axios, Recharts |
| Tests | pytest, Vitest + Testing Library, Ruff |
| Deployment | Docker, Docker Compose, Nginx, Render (backend), Vercel (frontend), GitHub Actions CI |

No OpenAI package or API key is used anywhere.

## Architecture

```
 Browser ──▶ React app (Vercel / Nginx) ──HTTPS + Bearer token──▶ FastAPI backend
                                                                      │
   Middleware: request ID → security headers → CORS → rate limit → body-size limit
                                                                      │
   api/routes  ──▶  permission check (role from DB)  ──▶  services  ──▶  repositories
                                                             │               │
                                     app/ml (scikit-learn) ──┤               ▼
                                     app/ai (Ollama, HF)  ───┘         PostgreSQL
                                                             │
                                     uploads/, trained_models/ (files)
```

- **Layers:** routes → services → repositories. `app/ml` and `app/ai` don't depend on FastAPI,
  so scripts and notebooks can reuse them.
- **Optional AI:** AI packages load lazily. The API starts without them; an endpoint that needs a
  missing piece returns a clear error saying what to install.
- **One error format:** `{"error": {"code": "...", "message": "...", "details": ...}}`, plus an
  `X-Request-ID` header on every response. Stack traces and secrets go only to the server log.

## Project structure

```
app/
  main.py                FastAPI app factory and middleware order
  api/routes/            auth, admin (audit log, settings), employees, datasets, models,
                         predictions, deployments, monitoring, drift, experiments,
                         explainability, jobs, ai, health, root
  api/deps.py            Dependencies: DB session, current user, require_permission()
  core/                  config (settings), permissions (roles), security (JWT, Argon2id),
                         middleware, error handlers, exceptions
  database/models/       users, employees, audit_logs, system_settings, datasets, ml_models,
                         deployments, drift, experiments, jobs
  models/                re-exports the ORM models (app.models)
  repositories/          data access (also re-exported as app.repository)
  services/              business logic: auth, role_slots (one-time sign-up), employees,
                         audit, settings, datasets, models, jobs, drift, explainability, ...
  ml/                    ingestion, validation, profiling, preprocessing, training,
                         persistence, prediction, synthetic data, visualization
  ai/                    Ollama chat, embeddings, classification, token counting, workflows
  schemas/               Pydantic request/response models
alembic/versions/        14 migrations (0001 … 0014_drift_results_jsonb)
frontend/                React app (src/pages, src/components, src/context, src/services)
scripts/                 create_super_admin, smoke_test, check_config, check_db,
                         backup_db, restore_db, run_worker, train_model, ...
tests/unit/              fast tests (SQLite test double, fakes for AI)
tests/integration/       migrations, app lifecycle, PostgreSQL (needs TEST_DATABASE_URL)
notebooks/               01_explore_dataset.ipynb (starter analysis + baseline model)
datasets/examples/       synthetic demo CSVs
main.py                  `python main.py` runs the API locally
render.yaml              Render blueprint (backend + PostgreSQL)
frontend/vercel.json     Vercel config (SPA routing, security headers)
Dockerfile, compose.yaml, compose.dev.yaml, .env.example
```

## Quick start (local)

**Prerequisites:** Python 3.12+, Git, PostgreSQL, Node.js 22 (for the frontend). Optional:
Ollama for LLM chat, Docker for containers.

**1. Clone and create a virtual environment**

```powershell
git clone https://github.com/Mehak-991/AI-ML-Project-.git
cd AI-ML-Project-
py -3.12 -m venv .venv
.\.venv\Scripts\activate               # Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
```

**2. Install packages**

| What | Command | Packages |
|---|---|---|
| Core + FastAPI + tests | `pip install -r requirements-dev.txt` | numpy, pandas, matplotlib, seaborn, scikit-learn, python-dotenv, openpyxl, fastapi, uvicorn, sqlalchemy, alembic, pydantic, python-multipart, pytest, ruff |
| Jupyter (optional) | `pip install -r requirements-notebook.txt` | notebook, jupyter, ipykernel |
| Deep learning (optional) | `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu` then `pip install -r requirements-nlp.txt` | torch (CPU), transformers, sentence-transformers, datasets, evaluate |
| LLM workflows (optional) | `pip install -r requirements-llm.txt` | langchain, langgraph, llama-index-core, tiktoken |

TensorFlow is not included (no code uses it, ~1.5 GB); install `tensorflow-cpu` yourself if
your notebooks need it.

**3. Configure**

```powershell
Copy-Item .env.example .env            # Linux/macOS: cp .env.example .env
```

Set at least:

```ini
DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/aimldb
JWT_SECRET_KEY=<output of: openssl rand -hex 32>
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.2:3b
```

**4. Create the database tables**

```powershell
alembic upgrade head
python scripts\check_config.py --db    # settings, folders, packages, DB connection, migration revision
```

**5. Run the backend**

```powershell
python main.py                         # or: uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs.

**6. Run the frontend** (new terminal)

```powershell
cd frontend
npm install
npm run dev                            # http://localhost:3000, proxies /api to port 8000
```

**7. Create the first accounts:** open the app → **Sign In** → **Create an Account** and choose
**Super Admin**, then **Admin**. Each is available only once. Or use the command line:

```powershell
python scripts\create_super_admin.py --email you@example.com --role super_admin
python scripts\create_super_admin.py --email admin@example.com --role admin
```

**Optional: LLM chat.** Install [Ollama](https://ollama.com), then `ollama pull llama3.2:3b`.

## Configuration

All settings come from environment variables, then `.env`. [.env.example](.env.example) lists
every variable. Invalid values stop startup with a clear `ConfigurationError` (secrets are never
printed).

| Area | Key variables |
|---|---|
| App | `APP_ENV` (development / testing / production), `DEBUG`, `DOCS_ENABLED`, `LOG_LEVEL`, `LOG_FORMAT` (text / json) |
| Auth | `JWT_SECRET_KEY` (≥ 32 bytes), `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`, `AUTH_BOOTSTRAP_VIA_REGISTRATION`, `METRICS_AUTH_TOKEN` |
| HTTP | `CORS_ORIGINS`, `MAX_REQUEST_BODY_MB`, `RATE_LIMIT_ENABLED`, `RATE_LIMIT_{DEFAULT,AI,TRAINING,AUTH}_PER_MINUTE`, `FORWARDED_ALLOW_IPS` |
| Database | `DATABASE_URL`, `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`, `DATABASE_CONNECT_TIMEOUT` |
| Storage / ML | `UPLOAD_DIR`, `MODEL_DIR`, `MAX_UPLOAD_SIZE_MB`, `MAX_DATASET_ROWS`, `MAX_DATASET_COLUMNS`, `MAX_PREDICTION_RECORDS` |
| LLM (Ollama) | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_ALLOWED_MODELS`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_NUM_CTX`, `OLLAMA_NUM_THREAD`, `OLLAMA_KEEP_ALIVE`, `OLLAMA_HEALTHCHECK_ENABLED` |
| Local models | `AI_DEVICE`, `AI_ALLOW_MODEL_DOWNLOADS`, `EMBEDDING_MODEL`, `CLASSIFIER_MODEL` |
| Frontend | `VITE_API_BASE_URL` (only when the frontend is hosted separately, e.g. on Vercel) |

**Production rules enforced at startup** (`APP_ENV=production`): `DATABASE_URL` must be
PostgreSQL, `DEBUG=false`, `CORS_ORIGINS` must not contain `*`, and `JWT_SECRET_KEY` must be at
least 32 bytes and not the default. Public sign-up never creates a Super Admin automatically in
production.

## Database and migrations

```powershell
alembic upgrade head          # apply all migrations
alembic current               # show the database revision
alembic downgrade -1          # roll back one revision
alembic upgrade head --sql    # print the SQL without running it
```

| Revision | Change |
|---|---|
| `0001`–`0011` | datasets, models, deployments, prediction logs, users and refresh tokens, drift, experiments, jobs, ownership, indexes |
| `0012_rbac_roles` | three roles; converts old roles `admin→super_admin`, `ml_engineer→admin`, `viewer→user`; role check constraint; session versioning. Reversible |
| `0013_employees_audit` | `employees`, `audit_logs`, `system_settings` tables |
| `0014_drift_results_jsonb` | aligns `drift_reports.results` to JSONB on PostgreSQL |

In Docker and on Render, migrations run automatically on startup (`RUN_MIGRATIONS=true`).

> A database created by an older, deleted set of migrations (stamped `0012`/`0013`) fails with
> `Can't locate revision`. Back it up, then run `alembic stamp --purge 0011 && alembic upgrade head`.
> Details: [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

**Backups:** `python scripts/backup_db.py` (checksummed dumps) and `python scripts/restore_db.py`.
Back up the database together with `uploads/` and `trained_models/`, because the rows point to
those files.

## API overview

All endpoints are under `/api/v1`. Interactive docs: `/docs`. Except for the public endpoints,
every request needs `Authorization: Bearer <access_token>` from `POST /auth/login`.

| Area | Endpoints | Who |
|---|---|---|
| Public | `GET /health`, `/api/v1/health`, `/api/v1/health/database`, `POST /auth/login`, `/auth/register`, `/auth/refresh`, `/auth/logout`, `GET /auth/registration-status` | anyone |
| Own account | `GET /auth/me`, `/auth/me/permissions`, `POST /auth/change-password` | signed in |
| Employees | `GET /employees`, `/employees/stats`, `/employees/{id}` · `POST /employees` · `PATCH /employees/{id}` · `DELETE /employees/{id}` | read: all · write: Admin+ · delete: Admin (own) / Super Admin |
| Users | `GET /auth/users` · `PATCH /auth/users/{id}` · `DELETE /auth/users/{id}` | Admin+ · Admin+ (limited) · Super Admin |
| Audit log | `GET /audit-logs` | Admin+ |
| Settings | `GET /settings` · `PATCH /settings` | all · Super Admin |
| Datasets | `GET /datasets`, `/datasets/{id}`, `/datasets/{id}/summary` · `POST /datasets`, `/datasets/validate` | read: all · upload: Admin+ |
| Models | `GET /models`, `/models/{id}` · `POST /models/train`, `/models/{id}/predict` | read: all · write: Admin+ |
| Deployments | `GET /deployments` · `POST /models/{id}/deploy`, `/undeploy` | read: all · Super Admin |
| Predictions | `GET /predictions/history`, `/models/{id}/predictions/history` · `POST .../ground-truth` | read: all · Admin+ |
| Monitoring & drift | `GET /monitoring/*`, `/drift/*` · `POST /drift/models/{id}/analyze-*` | read: all · Admin+ |
| Experiments & jobs | `GET /experiments`, `/jobs` · `POST` create/run/cancel/retry | read: all · Admin+ |
| Explainability | `/models/{id}/explainability/{summary,feature-importance,shap,lime}` | all |
| AI | `GET /ai/status`, `POST /tokens/count`, `/embeddings`, `/nlp/classify` · `POST /llm/chat`, `/nlp/analyze` | all · Admin+ |
| Metrics | `GET /metrics` (Prometheus) | protected by `METRICS_AUTH_TOKEN` when set |

**Common error codes:** `401` not signed in or session ended · `403 permission_denied` (the
required permission is in `error.details`) · `404 not_found` · `409` conflict (e.g. duplicate
email) · `422` validation · `429 rate_limited` · `503 maintenance_mode` / `database_unavailable`
· `502/504 provider_*` (Ollama).

## Training → prediction workflow

Requires an Admin or Super Admin account.

**PowerShell**

```powershell
$base = "http://127.0.0.1:8000/api/v1"
$login = Invoke-RestMethod -Method Post "$base/auth/login" -ContentType "application/json" `
  -Body (@{ email = "admin@example.com"; password = "<password>" } | ConvertTo-Json)
$h = @{ Authorization = "Bearer $($login.access_token)" }

$ds = curl.exe -s -H "Authorization: Bearer $($login.access_token)" `
  -F "file=@datasets/examples/synthetic_classification.csv" -F "name=demo" "$base/datasets" | ConvertFrom-Json
$model = Invoke-RestMethod -Method Post "$base/models/train" -Headers $h -ContentType "application/json" `
  -Body (@{ dataset_id = $ds.dataset.id; target_column = "label"; name = "demo-model" } | ConvertTo-Json)
$model.metrics.test

$records = @{ records = @(@{ num_a = 55.2; num_b = 0.7; num_c = 4; cat_a = "red"; cat_b = "small" }) } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post "$base/models/$($model.id)/predict" -Headers $h -ContentType "application/json" -Body $records
```

Or run the whole flow automatically (see [Testing](#testing)): `scripts/smoke_test.py`.

**Training options** (`POST /models/train`): `target_column`, optional `problem_type`
(auto-detected otherwise), `algorithm` (`linear` or `random_forest`), `feature_columns` /
`exclude_columns`, `test_size`, `validation_size`, `random_state`, `drop_duplicates`.

**Leakage controls:** the target is never a feature; duplicates are dropped before splitting;
imputation, scaling and encoding are fitted on the training split only; metrics are reported on
validation and test sets next to a dummy baseline.

**Model lifecycle:** every training run creates a new versioned artifact. Before loading, its
SHA-256 hash and scikit-learn version are checked; incompatible artifacts return `409
model_incompatible`.

Offline (no API or database): `python scripts/train_model.py datasets/examples/synthetic_classification.csv --target label`.
Notebook: `jupyter notebook notebooks/01_explore_dataset.ipynb`.

## AI / LLM (Ollama)

- **Local only, no API key.** `POST /llm/chat` and `POST /nlp/analyze` call an Ollama server.
  Default model `llama3.2:3b` (~2 GB download, ~3–4 GB RAM on CPU).
- **Setup:** install Ollama, run `ollama pull llama3.2:3b`, keep `OLLAMA_BASE_URL` pointing at it.
  With Docker: `docker compose --profile llm up -d`, then
  `docker compose exec ollama ollama pull llama3.2:3b`.
- **Failure handling:** Ollama down → `502 provider_unavailable`; model not pulled → `502
  provider_model_not_found` (with the `ollama pull` command); too slow → `504 provider_timeout`.
  The rest of the app keeps working. `/api/v1/health` reports `llm` as `ok`, `model_missing`,
  `unavailable` or `disabled`, but never fails because of it.
- **Online deployment:** the LLM is **disabled** on Render's free plan, which has 512 MB RAM. To
  enable it, run Ollama on a server with 8 GB+ RAM (a VPS) and set `OLLAMA_BASE_URL` on the
  backend.
- **Embeddings / sentiment** (`/embeddings`, `/nlp/classify`) need the optional PyTorch +
  transformers packages and download models on first use (`scripts/download_models.py`
  pre-downloads them).
- Prompts and answers are never logged unless `LLM_LOG_CONTENT=true`.

## Frontend

React + TypeScript + Vite + Tailwind in [frontend/](frontend/).

- **Pages:** Dashboard (role-specific), Employees, Datasets, Models, Experiments, Predictions &
  AI, Deployment & Monitoring, Drift, Explainability, Background Jobs, User Administration, Audit
  Log, System Settings.
- **Role-aware UI:** menus and buttons appear only when the role allows them. This is for
  convenience; the backend enforces every rule itself.
- **Sign-up form:** account type User / Admin / Super Admin; Admin and Super Admin show as
  "already registered" once their one-time account exists.
- **Sessions:** tokens are kept in `sessionStorage`; an expired session signs the user out with a
  notice.

```powershell
cd frontend
npm install
npm run dev        # development server on http://localhost:3000
npm run build      # production build into dist/
npm test           # role-based UI tests (Vitest)
npm run lint
```

When the frontend is hosted separately from the backend (Vercel), set `VITE_API_BASE_URL` to the
backend URL including `/api/v1`, and add the frontend URL to the backend's `CORS_ORIGINS`.

## Testing

### Automated tests

```powershell
.venv\Scripts\python -m pytest              # backend: unit + integration (500+ tests)
.venv\Scripts\python -m pytest tests/unit   # unit only
cd frontend; npm test; cd ..                # frontend role-based UI tests
ruff check .                                # lint
python -m pip check                         # dependency consistency
```

| Area | What is covered |
|---|---|
| RBAC | permission matrix for all three roles, privilege-escalation and mass-assignment attempts, token revocation, one-time Admin/Super Admin sign-up, Admin deletes only own employees |
| Employees | CRUD, validation, duplicates, sensitive-field hiding, manager hierarchy |
| Audit / settings | audit entries for sensitive actions, maintenance mode, sign-up toggle |
| ML | ingestion, validation, preprocessing, training, persistence, prediction, drift, explainability, jobs |
| AI | Ollama client with a mocked server (no model needed), error mapping, limits |
| Migrations | every revision with data, including the role conversion and its rollback |
| Frontend | role-based navigation, route guards, per-role buttons, sign-up options, session expiry |

Unit tests use an in-memory SQLite database as a stand-in. PostgreSQL integration tests need a
**disposable** database:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://user:<password>@localhost:5432/aiproject_test"; pytest -m integration
```

GitHub Actions runs lint, `pip-audit`, backend tests, migration tests, the frontend build/tests
and the Docker builds on every push.

### Smoke test against a running server

Logs in, then checks health, upload → train → predict, employee create/update/delete and the
audit log (needs an Admin or Super Admin account):

```powershell
$env:SMOKE_EMAIL = "admin@example.com"; $env:SMOKE_PASSWORD = "<password>"
python scripts\smoke_test.py https://aiml-backend-yrj8.onrender.com --cleanup
```

Every step should print `PASS`; the LLM step shows `SKIP` unless `--with-llm` is given and Ollama
is reachable.

### Manual testing checklist

Sign in once with each role (create a User account through sign-up) and check:

| Check | Super Admin | Admin | User |
|---|:-:|:-:|:-:|
| Employees list visible | ✅ | ✅ | ✅ |
| Salary / phone columns | ✅ | ✅ | hidden |
| "New employee" button | ✅ | ✅ | hidden |
| Delete button | every row | only own records | hidden |
| User Administration, Audit Log menus | ✅ | ✅ | hidden |
| Change System Settings | ✅ | read-only | read-only |
| Upload dataset / train model | ✅ | ✅ | hidden |

Also check: Admin/Super Admin are disabled in the sign-up form once created; a wrong password is
rejected; maintenance mode blocks an Admin's changes; actions show up in the Audit Log.

## Deployment

### Live deployment (Render + Vercel)

| Part | Platform | Config |
|---|---|---|
| Backend + PostgreSQL | Render (Docker, free plan) | [render.yaml](render.yaml) blueprint |
| Frontend | Vercel | [frontend/vercel.json](frontend/vercel.json) |

**Backend on Render**

1. Push the repo to GitHub, then open
   `https://render.com/deploy?repo=https://github.com/<owner>/<repo>` (or Render → New →
   Blueprint).
2. Render creates `aiml-backend` (Docker) and `aiml-db` (PostgreSQL) from `render.yaml`.
   `JWT_SECRET_KEY` and `METRICS_AUTH_TOKEN` are generated automatically; migrations run on
   every start.
3. After the frontend is deployed, set `CORS_ORIGINS` to the frontend URL (no trailing slash) in
   Render → aiml-backend → Environment.
4. Check `https://<backend>.onrender.com/api/v1/health` → `"database": "ok"`.

**Frontend on Vercel**

```powershell
cd frontend
vercel login
vercel link
vercel env add VITE_API_BASE_URL production    # https://<backend>.onrender.com/api/v1
vercel deploy --prod
```

Or import the repo in the Vercel dashboard with **Root Directory** `frontend` and the same
environment variable.

**Updates:** pushing to `main` redeploys the backend automatically. Redeploy the frontend with
`vercel deploy --prod`, or connect the repo in Vercel for automatic deploys.

**Free-plan limits:** the backend sleeps after ~15 minutes idle (first request ~1 minute); there
is no persistent disk, so uploaded datasets and trained models are lost on restart (database data
is kept); Render's free PostgreSQL expires after 30 days, so upgrade it or move to another
provider (e.g. Neon) and back up first; no LLM.

### Self-hosted (Docker Compose)

```bash
cp .env.example .env               # set POSTGRES_PASSWORD and JWT_SECRET_KEY (openssl rand -hex 32)
docker compose up -d --build       # db + migration + app + worker + frontend (Nginx on port 80)
docker compose --profile llm up -d # optional: Ollama
docker compose exec ollama ollama pull llama3.2:3b
docker compose run --rm app python scripts/create_super_admin.py --email you@example.com
docker compose ps                  # all services should become "healthy"
docker compose logs -f app
docker compose stop                # stop; data is kept in volumes
```

Never run `docker compose down -v` on a real deployment: it deletes the database and file volumes.

- The images run as a non-root user with a read-only filesystem; the database is on an internal
  network with no published port; only the Nginx frontend is published.
- Put HTTPS in front (Caddy, Nginx with Let's Encrypt, or a load balancer), then enable HSTS in
  `frontend/nginx.conf`.
- Full guide incl. backups, first Super Admin, migration procedure and a go-live checklist:
  [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## Security

**In place**

- Backend permission checks on every protected endpoint; role read from the database only.
- Argon2id password hashing; old PBKDF2/bcrypt hashes are upgraded at the next login.
- Short-lived access tokens, rotating single-use refresh tokens, immediate revocation on password
  change, role change or deactivation.
- Strict request schemas (unknown fields rejected) against mass assignment; role values enforced
  by a database constraint.
- Audit log of sensitive actions (passwords, tokens and salaries are never written to it).
- Rate limiting (stricter on login and account endpoints), request-size limits, security headers
  (CSP, HSTS on Vercel, X-Frame-Options, nosniff), restrictive CORS.
- Safe uploads (type sniffing, size limits, hardened Excel parsing, generated file names) and
  hash-checked model artifacts.
- Errors never expose stack traces, SQL or secrets; secrets come only from environment
  variables and are never committed.

**Not included**

- Multi-factor authentication, account lockout and password-reset e-mails.
- Rate limits shared across multiple servers (limits are per process).
- Malware scanning of uploads; deleting datasets/models through the API.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ConfigurationError: Invalid configuration` | Fix the listed variables; run `python scripts/check_config.py` |
| `relation "..." does not exist` / 500 on every database endpoint | Migrations haven't run: `alembic upgrade head` (Docker/Render run them on start) |
| `Can't locate revision '0013'` | Old migration history: back up, then `alembic stamp --purge 0011 && alembic upgrade head` |
| 401 "Session is no longer valid" | Password or role changed, or account deactivated: sign in again |
| 403 `permission_denied` | The role lacks the permission named in `error.details.required_permission` |
| Admin/Super Admin not offered at sign-up | That one-time account already exists; ask the Super Admin to grant the role |
| 503 `maintenance_mode` | A Super Admin turned on maintenance mode in System Settings |
| Browser blocks API calls (CORS error) | Add the exact frontend URL to the backend's `CORS_ORIGINS` |
| First request to the live app is slow | Render free plan was asleep; wait about a minute |
| 502 `provider_unavailable` on chat | Start Ollama (`ollama serve`) and check `OLLAMA_BASE_URL` |
| 502 `provider_model_not_found` | `ollama pull llama3.2:3b` |
| 429 `rate_limited` | Wait for `Retry-After` seconds |
| 409 `model_incompatible` | Retrain with the current scikit-learn version |

## Known limitations

- LLM chat is not available on the free online deployment (needs a server with more RAM).
- On Render's free plan, uploaded files and trained models are not persistent, and the free
  database expires after 30 days.
- Datasets and models can't be deleted through the API.
- LLM responses are not streamed; LlamaIndex is installed but no RAG feature uses it yet.
- Tabular ML only: datetime and free-text columns are excluded rather than engineered; no
  hyperparameter search.
- No static type checking (mypy/pyright) is configured.

## Verification status

| Area | Status |
|---|---|
| Backend tests (unit + integration without external services) | ✅ passing |
| Frontend: type check, production build, Vitest tests | ✅ passing |
| CI-equivalent run in a clean environment (lint, `pip-audit`, unit and migration tests) | ✅ passing |
| PostgreSQL: full migration chain on an empty database, schema identical to the models | ✅ |
| Role conversion migration on a copy of real data, with rollback | ✅ |
| Docker: images built and full stack healthy in an isolated staging run, incl. restart persistence | ✅ |
| Live deployment (Render + Vercel): health, login per role, employee create/delete, CORS | ✅ |
| Real Ollama chat (`llama3.2:3b`, local) | ✅ |
| Ollama Docker container | ⚠️ not run (image download too slow during verification) |
| PostgreSQL integration tests (`TEST_DATABASE_URL`) | ⚠️ 10/11 pass; one test fails in its own test harness (pre-existing) |
| Embeddings / classification with real models | ⚠️ not run; covered by fakes |
