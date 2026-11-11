# Local Development and Docker Startup

This is the shortest verified path to a working copy on your own machine. For production see
[DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md); every variable is described in
[ENVIRONMENT_SETUP.md](../ENVIRONMENT_SETUP.md).

## A. Everything in Docker (recommended for demos)

Requirements: Docker Desktop (Compose v2), about 4 GB of free RAM.

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD and JWT_SECRET_KEY (openssl rand -hex 32), METRICS_TOKEN is optional
docker compose up -d --build
docker compose ps                     # db, app, worker and frontend should become "healthy"
```

Create the first superadmin once (there is no way to create one from the web):

```bash
docker compose run --rm --no-deps -it app python scripts/create_superadmin.py --email you@example.com
# a hidden prompt asks for the password twice; nothing is echoed or stored in .env
```

Open <http://localhost/> and sign in. Health: <http://localhost/api/v1/health>.
Set `DOCS_ENABLED=true` in `.env` and recreate `app` if you want <http://localhost/docs>.

Stop without losing data: `docker compose stop` (or `docker compose down`).
**Never** add `-v` to `down`: that deletes the database, uploads and trained models.

## B. Backend and frontend on the host (development)

Requirements: Python 3.12, Node 22, and a PostgreSQL 18 database (the dev overlay starts one).

```bash
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -c requirements.lock -r requirements.txt -r requirements-dev.txt

docker compose -f compose.yaml -f compose.dev.yaml up -d db   # PostgreSQL on 127.0.0.1:5433
# in .env: DATABASE_URL=postgresql+psycopg://aiproject:<POSTGRES_PASSWORD>@127.0.0.1:5433/aiproject
alembic upgrade head
python scripts/create_superadmin.py --email you@example.com
uvicorn app.main:app --reload                          # http://127.0.0.1:8000

cd frontend && npm ci
VITE_DEV_API_TARGET=http://127.0.0.1:8000 npm run dev   # http://localhost:5173
```

## C. Quality checks (what CI runs)

```bash
ruff check .                                   # lint + security rules (pyproject.toml)
pytest tests/unit -q                           # no database needed (SQLite test double)
# PostgreSQL integration tests need a disposable database that is already migrated:
TEST_DATABASE_URL=postgresql+psycopg://user:pass@127.0.0.1:5433/aiproject_test \
  DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
TEST_DATABASE_URL=... pytest tests/integration -q
pip-audit -r requirements.lock --no-deps --disable-pip
cd frontend && npm run lint && npm run build && npm audit --audit-level=high
python scripts/check_tracked_files.py          # no dumps/keys/.env tracked
```

Never point the integration tests at a database that holds real data.

## D. Full-stack end-to-end check (disposable stack only)

`scripts/e2e_check.py` creates users and data. Run it only against a throw-away deployment with its
own superadmin (see the docstring of the script):

```bash
E2E_SUPERADMIN_EMAIL=... E2E_SUPERADMIN_PASSWORD=... \
  python scripts/e2e_check.py --base-url http://127.0.0.1:18099 --confirm-disposable
python scripts/check_stack.py --origin http://127.0.0.1:18099
```

## E. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `required variable APP_VERSION is missing` | Add `APP_VERSION=local-dev` to `.env` (it has no default on purpose) |
| `required variable JWT_SECRET_KEY / POSTGRES_PASSWORD` | Set both in `.env` |
| `Pool overlaps with other one on this address space` | Another stack uses the default `172.21.0.0/16`; set `FRONTEND_SUBNET` and `FRONTEND_PROXY_IP` in `.env` |
| Sign-in works but pages say "forbidden" | The account is a `user`; ask a superadmin for the `admin` role |
| `create_superadmin.py` says migrations are missing | Run `alembic upgrade head` (Docker does this in the `migration` service) |
| Browser shows a network error on registration in dev | Set `VITE_DEV_API_TARGET` for the Vite proxy (see `frontend/vite.config.ts`) |
| Training stays "pending" | The worker is not running or unhealthy: `docker compose logs worker` |
| Port 80 already in use | Set `FRONTEND_PORT=8080` in `.env` |
