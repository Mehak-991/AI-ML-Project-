# AIProject

Foundation for a modular, production-oriented AI/ML platform: FastAPI REST API,
typed configuration, SQLAlchemy 2.x + PostgreSQL (psycopg 3), Alembic migrations,
pytest test suite and Ruff linting. ML, deep learning, LLM and RAG features are
added in later phases on top of this structure.

## Project layout

```
app/
  api/routes/        HTTP route modules (root.py, health.py); api/router.py aggregates v1
  core/              config.py (settings), exceptions.py, error_handlers.py
  database/          base.py (DeclarativeBase), session.py (engine/session), models/
  schemas/           Pydantic request/response models
  services/          Business logic (health_service.py)
  repositories/      Data-access layer (Part 2+)
  utils/             Logging and helpers
  main.py            App factory `create_app()` and ASGI `app`
alembic/             Migration environment (reads DATABASE_URL from settings)
tests/unit/          Fast tests, no external services
tests/integration/   Lifecycle tests; PostgreSQL tests run only if TEST_DATABASE_URL is set
datasets/ notebooks/ uploads/ trained_models/ logs/   Data and artifacts (git-ignored contents)
scripts/             Utility scripts (check_health.py)
```

## Prerequisites

- Python **3.12+** (`python --version` or, on Windows, `py -0` to list installed versions)
- Git
- PostgreSQL 14+ — optional for development; required when `APP_ENV=production`

## Setup — Windows PowerShell

```powershell
cd "C:\path\to\AIProject"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

If activation fails with *"running scripts is disabled on this system"*, run once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

## Setup — Linux / macOS

```bash
cd /path/to/AIProject
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
cp .env.example .env
```

## Dependencies

| Group | Install | Contents |
|---|---|---|
| Core runtime | `pip install -r requirements.txt` | FastAPI, Uvicorn, Pydantic, pydantic-settings, python-dotenv, SQLAlchemy, psycopg, Alembic |
| Dev & test | `pip install -r requirements-dev.txt` | Core + pytest, pytest-cov, HTTPX, Ruff |
| ML (later) | `pip install -e ".[ml]"` | NumPy, pandas, scikit-learn, joblib |
| LLM (later) | `pip install -e ".[llm]"` | OpenAI SDK, tiktoken |

No GPU libraries are installed. Install PyTorch separately in a later phase using the
selector at pytorch.org for your CPU/CUDA target.

## Configuration

Settings are read from environment variables first, then from `.env`
(see [app/core/config.py](app/core/config.py)).

| Variable | Default | Notes |
|---|---|---|
| `APP_NAME` | `AIProject` | Shown in docs and responses |
| `APP_ENV` | `development` | `development`, `testing` or `production` |
| `DEBUG` | `false` | Must be `false` in production |
| `API_V1_PREFIX` | `/api/v1` | Must start with `/` |
| `LOG_LEVEL` | `INFO` | |
| `CORS_ORIGINS` | localhost:3000 in dev, none in prod | Comma-separated; `*` rejected in production |
| `DATABASE_URL` | unset | `postgresql+psycopg://user:pass@host:5432/db`; required in production |
| `DATABASE_CONNECT_TIMEOUT` | `5` | Seconds |
| `OPENAI_API_KEY` | unset | Used in later phases |

Invalid settings stop the app at startup with a `ConfigurationError` that lists each
problem, without echoing secret values. `DATABASE_URL` and `OPENAI_API_KEY` are held
as `SecretStr` and are masked in logs and reprs. `.env` is git-ignored; never commit it.

## Running the application

```bash
uvicorn app.main:app --reload
```

| URL | Purpose |
|---|---|
| http://127.0.0.1:8000/ | Welcome message |
| http://127.0.0.1:8000/health | Liveness: the process is up, no dependency checks |
| http://127.0.0.1:8000/api/v1/health | Readiness: includes a database check and returns 503 if a configured DB is unreachable |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/redoc | ReDoc |

With the server running, a quick smoke check is `python scripts/check_health.py`.

All errors share one envelope:

```json
{"error": {"code": "not_found", "message": "Not Found"}}
```

Unhandled exceptions are logged server-side and return a generic 500 without internal details.

## Database migrations

Set `DATABASE_URL` in `.env`, then:

```bash
alembic revision --autogenerate -m "describe change"   # after adding models
alembic upgrade head
```

Register new model modules in [app/database/models/\_\_init\_\_.py](app/database/models/__init__.py)
so autogenerate can see them.

## Running tests and lint

```bash
pytest                       # all tests
pytest tests/unit            # unit tests only
pytest --cov=app             # with coverage
ruff check .                 # lint
ruff format .                # format (use --check in CI)
```

PostgreSQL integration tests are skipped unless `TEST_DATABASE_URL` points at a
**disposable** database:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/aiproject_test"; pytest -m integration
```
```bash
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/aiproject_test pytest -m integration
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `ModuleNotFoundError: No module named 'app'` | Run commands from the project root, with the venv active |
| `uvicorn: command not found` | Activate the venv, or run `python -m uvicorn app.main:app --reload` |
| `ConfigurationError: Invalid configuration -> ...` | Fix the listed variables in `.env` or the environment |
| `/api/v1/health` returns 503 | PostgreSQL is unreachable; check that it's running and that `DATABASE_URL` is correct |
| `No module named 'psycopg2'` | Use the `postgresql+psycopg://` scheme (plain `postgresql://` is normalized automatically) |
| Port 8000 in use | `uvicorn app.main:app --reload --port 8001` |
| The path contains spaces (Windows) | Quote it: `cd "C:\path with spaces\AIProject"` |
