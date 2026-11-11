# Contributing

## Ground rules

* Work on a branch and open a pull request; merge with a **merge commit** (no squash, no rebase of
  shared branches). Never force-push and never rewrite published history.
* Never commit `.env*` files (except the `.example` ones), database dumps, backups, trained models
  or uploads. `python scripts/check_tracked_files.py` and the gitleaks job enforce this.
* Do not weaken a security check to make a test pass. If a test fails, fix the cause.
* A new API route **must** declare the permission it needs (`require_permission(...)` aliases in
  `app/api/deps.py`) or be marked public. A route with no declaration is refused for everyone, and
  `tests/unit/test_rbac_matrix.py` fails until you add the route to the matrix.
* A schema change needs an Alembic migration that is safe on a populated database, plus a test.
  Migrations that change role semantics are rolled out expand → migrate → contract; do not rely on
  a production downgrade as a rollback.

## Setup and checks

See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md). Before opening a pull request:

```bash
ruff check .
pytest tests/unit -q
cd frontend && npm run lint && npm run build
```

Changes that touch the database should also pass `tests/integration` against a disposable,
migrated PostgreSQL.

## Conventions

* Backend layering: `api/routes` (HTTP only) → `services` (use cases) → `repositories`
  (queries) → SQLAlchemy models. Keep ML code in `app/ml`.
* Request and response bodies are Pydantic models with `extra="forbid"` for inputs.
* Errors use the shared `{"error": {"code", "message"}}` shape; never return stack traces.
* Never log passwords, tokens or secrets.
* Frontend: TypeScript strict mode, calls only through `frontend/src/services/api.ts`, and gates UI
  with `can(permission)` from `AuthContext` (a hint only; the API is the authority).
* Tests live in `tests/unit` (no external services) and `tests/integration` (real PostgreSQL).

## Commit messages

Short imperative summary (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`), then a body that says
why. Mention migrations and any manual rollout step.
