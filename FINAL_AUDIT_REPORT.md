# Final Audit Report: AIProject (after Parts 1–4)

| | |
|---|---|
| Date | 2026-10-28 |
| Version audited | 0.4.0 (git `8ef00e2` + audit fixes listed in §9) |
| Environment | Windows 11, Python 3.12.2 (`.venv`), Git Bash/PowerShell |
| Scope | Code quality, API, database, ML, LLM/DL, deployment, security |
| Status legend | **PASS** verified by execution · **FAIL** defect found and still open · **BLOCKED** couldn't run in this environment · **NOT TESTED** deliberately not run |

---

## 1. Executive summary

The application works end to end for everything this environment could execute:

- **Tests and lint:** 320 automated tests pass (3 skipped: real PostgreSQL), with 97% line
  coverage. Ruff lint and format checks are clean.
- **Live server:** started with the documented `uvicorn app.main:app` command, it passed
  **38/38 live checks**: core endpoints, Swagger, dataset validation and upload, training,
  prediction, model reload, token counting, the embeddings 503 path, LLM chat and LLM errors
  through a local fake provider, and the request-size limit.
- **Defects:** the audit found and **fixed 5 defects**, including one Medium security issue
  (tracebacks returned to clients when `DEBUG=true`). There are **no open FAIL items**.

Not verified, because the environment didn't allow it:

- real PostgreSQL (no credentials);
- the Docker image build and run (daemon not running);
- local transformer/embedding models (PyTorch not installed; large downloads avoided);
- real OpenAI calls (no key, and paid calls are prohibited).

**The project is not production-ready:** it has **no authentication or authorization** (H1).
That is the main blocker before any network exposure.

| Area | Result |
|---|---|
| Code quality | **PASS** |
| API | **PASS** |
| Database | **PASS** (SQLite stand-in) / **BLOCKED** (PostgreSQL) |
| ML workflow | **PASS** |
| LLM (mocked provider) | **PASS** |
| Deep learning / embeddings (real models) | **NOT TESTED** |
| Docker config | **PASS** (static) / **BLOCKED** (build/run) |
| Security | 1 High open (no auth), 2 Medium open, 2 Medium fixed; details in §8 |

---

## 2. Test and lint results

| Check | Command | Status | Evidence |
|---|---|---|---|
| Full test suite | `python -m pytest -q` | **PASS** | `320 passed, 3 skipped in 22.5s` (skips: `TEST_DATABASE_URL not set`) |
| Coverage | `python -m pytest -q --cov=app` | **PASS** | `TOTAL 2633 stmts, 78 missed, 97%` |
| Ruff lint | `ruff check .` | **PASS** | `All checks passed!` |
| Ruff format | `ruff format --check .` | **PASS** | `108 files already formatted` |
| Syntax / compile | `python -m compileall -q app scripts alembic tests` | **PASS** | no errors |
| Dependency consistency | `python -m pip check` | **PASS** | `No broken requirements found.` |
| Configuration | `python scripts/check_config.py` | **PASS** | `PASSED (0 error(s))` |
| Type checking | n/a | **NOT TESTED** | No mypy/pyright configuration exists in the repository |
| Circular imports / missing modules | each of the 66 `app.*` modules imported in its own fresh interpreter | **PASS** | `modules imported in isolation: 66, failures: 0` |
| Optional AI imports at startup | `import app.main` and inspect `sys.modules` | **PASS** | torch, transformers, sentence_transformers, openai, tiktoken and langgraph are not imported at startup |
| Dead code | AST scan of `app/` definitions vs. references | **PASS (after fix)** | `MLModelRepository.list_versions` had zero references and was removed. Test-only helpers kept (`EmbeddingService.batches_for`, `DatasetRepository.get_by_sha256`, `clear_artifact_cache`). `ConflictError` was unused and is now used by the DB error handler |
| Duplicate implementations | manual review | **PASS** | No duplicated logic. `scripts/check_health.py` is a subset of `scripts/smoke_test.py` (Info) |
| API schema consistency | OpenAPI inspection + new test `test_openapi_error_schemas_match_real_envelope` | **PASS (after fix D4)** | Before the fix, routes documented 422 as FastAPI's `HTTPValidationError` (`{"detail": [...]}`), but the API returns `{"error": {...}}`. All 4xx/5xx now document `ErrorResponse`; 18 operations, no duplicate operation IDs |

---

## 3. API verification

The server was started with the documented command plus test-only environment variables:
`DATABASE_URL=sqlite:///…` (a migrated stand-in), scratch `UPLOAD_DIR`/`MODEL_DIR`,
`OPENAI_BASE_URL=http://127.0.0.1:8792/v1` (a **local fake OpenAI server**), a dummy
`OPENAI_API_KEY`, and `RATE_LIMIT_TRAINING_PER_MINUTE=60`:

```
python -m uvicorn app.main:app --port 8803
python <scratchpad>/audit_api.py http://127.0.0.1:8803 http://127.0.0.1:8792   ->  38 PASS, 0 FAIL
python scripts/smoke_test.py http://127.0.0.1:8803                           ->  10 ok/skipped, 0 failed
```

| Check | Status | Evidence |
|---|---|---|
| `GET /` | **PASS** | 200, `version=0.4.0` |
| `GET /health` | **PASS** | 200, `status=ok` |
| `GET /api/v1/health` | **PASS** | 200, `components={'database': 'ok'}` |
| `GET /docs` (Swagger UI) | **PASS** | 200, swagger-ui HTML; `/openapi.json` 200, 17 paths |
| Request ID + security headers | **PASS** | `X-Request-ID` present; `X-Content-Type-Options: nosniff` |
| `POST /datasets/validate` | **PASS** | 200, valid=True, warnings `['duplicate_rows']`, 10 missing cells reported |
| `POST /datasets` | **PASS** | 201, 255 rows × 6 cols |
| Invalid uploads | **PASS** | `evil.exe` → 415 `unsupported_file_type`; `../../etc/passwd.csv` (empty) → 400 `invalid_file`; text named `.xlsx` → 400; duplicate header → 422 |
| `GET /datasets/{id}/summary` | **PASS** | 200 |
| Training / prediction | **PASS** | see §5 |
| Token counting | **PASS** | real tiktoken: 9 tokens, `o200k_base`, `approximate=false` |
| Embeddings (no torch installed) | **PASS** | 503 `optional_dependency_missing` with the PyTorch install command |
| LLM chat / provider errors | **PASS** | see §6 |
| Missing model | **PASS** | 404 `not_found` |
| Missing credentials | **PASS** | separate instance with no key: `/llm/chat` and `/nlp/analyze` → 503 `provider_not_configured` ("Set OPENAI_API_KEY in .env…") |
| Request size limit | **PASS** | 6 MB JSON → 413 `request_too_large` |
| Rate limiting | **PASS** | first audit run: the 11th upload/train request within a minute got **429** (access log `POST /api/v1/models/train 429`); the bucket refilled later |
| Secrets in server log | **PASS** | `grep -c "sk-audit-fake\|not-a-real-key" server.log` → `0` |

---

## 4. Database verification

| Check | Status | Evidence |
|---|---|---|
| PostgreSQL connectivity | **BLOCKED** | PostgreSQL 18 is listening on `localhost:5432`, but no test credentials were provided (`TEST_DATABASE_URL` unset, no `.env`). Not attempted with guessed credentials |
| Migrations against disposable PostgreSQL | **BLOCKED** | as above. The PostgreSQL DDL was rendered offline in Part 4 (`alembic upgrade head --sql`) and reviewed |
| Alembic revision graph | **PASS** | `alembic heads` → `0002 (head)` (single head); `alembic history` → `<base> -> 0001 -> 0002` |
| Migration execution (SQLite stand-in) | **PASS** | fresh DB: `alembic upgrade head` ran 0001 and 0002; `alembic current` → `0002 (head)`; `alembic check` → `No new upgrade operations detected.` |
| Upgrade with data, backfill, downgrade | **PASS** | `tests/integration/test_migrations.py`: versions backfilled `[('churn',1),('churn',2),('other',1)]`, `compare_metadata == []`, downgrade to base |
| Session cleanup / rollback | **PASS** | `test_get_db_closes_session`, `test_get_db_rolls_back_on_error`, `test_session_rollback_discards_changes` |
| Unreachable database (live) | **PASS** | `DATABASE_URL` → closed port: `/api/v1/health` 503 `{"database":"unavailable"}`; `/api/v1/datasets` 503 `database_unavailable`; `/health` still 200; user, host and password not in the response or the log (grep count 0) |
| DB error mapping | **PASS** | unit tests: `OperationalError` → 503 `database_unavailable`, `IntegrityError` → 409 `conflict`, driver text not leaked |
| Wrong credentials at container start | **PASS** | entrypoint fails fast in Part 4: `database check failed (authentication_failed)` |
| No real database modified | **PASS** | only SQLite files in the scratch directory were created or changed |

---

## 5. ML workflow results

The training data is the seeded synthetic set from `app/ml/synthetic.py` (250 rows + 5 duplicates,
injected missing values).

| Check | Status | Evidence |
|---|---|---|
| Reproducible training | **PASS** | classification v1: test accuracy 0.94 vs majority baseline 0.50, macro-F1 0.940, ROC AUC 0.973. Retraining with the same seed gave **identical** test metrics, as `version 2` |
| Train/test separation | **PASS** | rows: raw 255, duplicates dropped 5 (before splitting), train 150 / validation 50 / test 50. Unit test `test_preprocessing_is_fitted_on_training_split_only` |
| Preprocessing | **PASS** | unit tests for imputation, scaling, one-hot with unseen categories, and type coercion |
| Problem-type-appropriate metrics | **PASS** | regression (random forest): R² 0.859, RMSE 10.32 vs baseline RMSE 27.45, and no accuracy metric reported |
| Serialization + reload | **PASS** | artifact reloaded in a **separate fresh process** from `MODEL_DIR` (hash-verified): predictions `['yes','no']` and probabilities identical to the live API |
| Missing artifact | **PASS** | file deleted → 500 `model_artifact_error`, "file is missing", no path leaked |
| Tampered artifact | **PASS** | bytes appended → 500 `model_artifact_error`, "failed its integrity check" |
| Incompatible model | **PASS** | unit tests: different sklearn major.minor → 409 `model_incompatible` **before unpickling**; garbage or wrong-format artifact → 409 |
| Feature-schema mismatch / invalid input | **PASS** | unknown feature, missing feature, wrong type, and null without `allow_missing` → 422 `data_validation_error`; empty records → 422 `validation_error`; `allow_missing=true` → 200 |
| Wrong problem type | **PASS** | text target with `problem_type=regression` → 422 `training_error` |

---

## 6. LLM and deep-learning verification

No paid API calls were made. LLM behaviour was exercised (a) in unit tests, using the real
OpenAI SDK against an in-memory HTTP transport, and (b) live, against a local fake
OpenAI-compatible server.

| Check | Status | Evidence |
|---|---|---|
| Missing API key | **PASS** | 503 `provider_not_configured` (live and unit tests); the app starts normally |
| Mocked completion | **PASS** | live `/llm/chat` → 200, `finish=stop`, `usage.total_tokens=15` |
| Rate limit | **PASS** | 429 `provider_rate_limited`, `Retry-After: 3` |
| Quota | **PASS** | 429 `provider_quota_exceeded` |
| Authentication failure | **PASS** | 502 `provider_authentication_failed` (not retried) |
| Provider 5xx | **PASS** | 502 `provider_unavailable` |
| Timeout | **PASS** | 504 `provider_timeout` after the configured 2 s timeout plus 1 retry |
| Provider error text not leaked | **PASS** | `provider text leaked=False` for every error case |
| Request hygiene | **PASS** | fake provider saw `Authorization: Bearer` on every request and `store=false`; retries bounded (`OPENAI_MAX_RETRIES=1` → 2 attempts) |
| Input limits before any call | **PASS** | model outside the allow-list → 422; a 45,000-character prompt → 422 (`LLM_MAX_INPUT_CHARS=32000`); token cap covered by unit tests |
| LangGraph workflow | **PASS** | live `/nlp/analyze` (mocked provider, no sentiment) → 200 |
| Optional dependency handling | **PASS** | subprocess test with every AI package blocked: app serves, AI endpoints return 503 with install hints, no AI module imported; namespace-package detection tests |
| Embedding dimensions and batching | **PASS (fakes)** / **NOT TESTED (real model)** | unit tests verify shape, dimension pinning, batch splitting `[4,4,2]` and non-finite rejection. Real Sentence Transformers not run: PyTorch isn't installed, and the large download was avoided per the audit rules |
| Sentiment classifier (real model) | **NOT TESTED** | same reason; covered by fakes |
| GPU usage | **NOT TESTED** | none used, by design |

**Low finding (open):** the OpenAI SDK also retries `insufficient_quota` 429s, which can never
succeed (fake provider: `AUDIT_QUOTA: 2` requests). That costs one extra request and some
latency per call. See L2.

---

## 7. Docker verification

| Check | Status | Evidence |
|---|---|---|
| Compose syntax | **PASS** | `docker compose config --quiet` and `-f compose.yaml -f compose.dev.yaml config --quiet` both valid |
| Required secret enforced | **PASS** | without `POSTGRES_PASSWORD`: `required variable POSTGRES_PASSWORD is missing a value` |
| DB not publicly exposed | **PASS** | `db` has no `ports`; `backend` network is `internal: true`; dev overlay binds `127.0.0.1:5433` only |
| App exposure | **PASS** | published on `host_ip: 127.0.0.1` only |
| Persistent storage | **PASS** | named volumes `pgdata`, `uploads`, `models`, `model_cache` |
| Health checks / startup order | **PASS** | db `pg_isready`; app `depends_on: condition: service_healthy`; image `HEALTHCHECK` on `/health` |
| Container hardening | **PASS** | `USER app` (uid 10001), `read_only: true`, `tmpfs /tmp`, `cap_drop: ALL`, `no-new-privileges` |
| No secrets in image | **PASS** | `.dockerignore` excludes `.env` and `.env.*`; no `ARG`/`ENV` with secrets; `COPY` limited to `app/`, `alembic/`, `scripts/`, `alembic.ini` |
| Entrypoint logic | **PASS** | Part 4 run locally: invalid prod config → exit 2; migrations applied then exec; wrong credentials → fail fast |
| Env-variable handling | **PASS (after fix D3)** | `FORWARDED_ALLOW_IPS` is now configurable (was hard-coded to `127.0.0.1` in `CMD`) |
| Image build | **BLOCKED** | `docker info` → `failed to connect to the docker API … dockerDesktopLinuxEngine` (Docker Desktop not running) |
| `docker compose up` + health | **BLOCKED** | same |

---

## 8. Security findings (by severity)

| ID | Severity | Finding | Status |
|---|---|---|---|
| H1 | **High** | **No authentication or authorization.** Anyone who can reach the API can upload data, train models (CPU), and spend LLM budget | **Open.** Must be added (gateway OIDC/API keys) before any network exposure |
| M1 | Medium | With `DEBUG=true`, Starlette returned **full tracebacks and exception text** in 500 responses (verified: `traceback/detail exposed=True`). Production already rejected `DEBUG=true`, but dev/staging hosts could leak internals | **Fixed (D1).** `debug=False` always; `DEBUG` now only raises log verbosity. Regression test added |
| M2 | Medium | **Pickle trust boundary.** joblib artifacts execute code on load. Mitigations: loaded only from `MODEL_DIR` by generated name, after a SHA-256 check and a sklearn-version check. The hash lives in the same database, so an attacker with DB **and** `MODEL_DIR` write access can still run code | **Open (accepted, documented).** Recommend HMAC-signing artifacts with a key held outside the DB |
| M3 | Medium | **Resource exhaustion through training.** No wall-clock limit on training; a random forest on 200k×500 data can occupy a worker for minutes. Only the training rate limit (10/min per IP) bounds it | **Open.** Recommend a job queue with time limits |
| M4 | Medium | The container trusted `X-Forwarded-For` only from a hard-coded `127.0.0.1`, so behind a proxy container every client shared one rate-limit bucket | **Fixed (D3).** `FORWARDED_ALLOW_IPS` is configurable and documented |
| L1 | Low | A malformed or hostile `.xlsx` raised an untranslated XML `ParseError` → 500 instead of 400. Entity-expansion ("billion laughs") was **already blocked** by Python's expat 2.5 (rejected in 1.4 s, ~59 MB peak) | **Fixed (D2).** All parser failures → 400 `invalid_file`; `defusedxml` added (openpyxl `DEFUSEDXML=True`); regression tests |
| L2 | Low | OpenAI SDK retries non-retryable `insufficient_quota` 429s | **Open** (extra request only) |
| L3 | Low | Rate limits and model cache are per process (2 workers in the image ≈ 2× the limit) | **Open (documented)** |
| L4 | Low | No dependency lock file (version ranges only); base images not pinned by digest | **Open.** Recommend `pip-tools`/`uv` lock and digest pins |
| L5 | Low | Uploaded files and models are kept indefinitely; no delete/retention endpoint | **Open** |
| L6 | Low | No CVE scan of dependencies (`pip-audit` not installed) | **NOT TESTED** |
| I1 | Info | `/ai/status`, `/docs` and `/openapi.json` disclose installed packages, model names and API shape. `DOCS_ENABLED=false` is available | Documented |
| I2 | Info | Test files contain fake key-like strings (`sk-test-…`, `sk-must-not-leak`) used to assert non-leakage | Not secrets |

**Checks that passed (no finding):**

| Check | Evidence |
|---|---|
| Hardcoded secrets | Scan of tracked files found only fake test fixtures; git history scan: `0` real-looking keys. Only `.env.example` was ever committed |
| Unsafe uploads / path traversal | Server-generated names, `resolve_within` rejects `..`, separators, absolute paths and symlinks (tests + live `../../etc/passwd.csv`). Content sniffing, size limit while streaming, zip-ratio limit |
| CORS | No origins by default in production; `*` rejected at startup (tests) |
| Exposed exception details | Generic 500 body; DB/provider/driver text only in logs (live checks, M1 fixed) |
| Arbitrary model paths | API can't choose model files or HF repos (`EMBEDDING_MODEL`/`CLASSIFIER_MODEL` are server settings, `trust_remote_code=False`). LLM `model` restricted to an allow-list. Artifacts addressed by DB id only |
| Secrets in logs | API key and prompts never logged; SDK debug logging muted (unit test); live server log grep `0` |

---

## 9. Defects fixed during this audit

| ID | Defect | Fix | Files | Verification |
|---|---|---|---|---|
| D1 | `DEBUG=true` returned tracebacks to clients (M1) | Never enable Starlette debug responses; `DEBUG` → verbose logging only | `app/main.py`, `.env.example`, `README.md` | new `test_debug_mode_never_returns_tracebacks`; full suite |
| D2 | Malformed/hostile XLSX → 500; no XML hardening (L1) | Translate any parser failure to 400 `invalid_file`; add `defusedxml` | `app/ml/ingestion.py`, `requirements.txt`, `pyproject.toml` | new `test_hostile_xlsx_is_rejected_as_invalid_file[malformed-xml, entity-bomb]`, `test_defusedxml_hardening_is_active` |
| D3 | Container proxy trust hard-coded (M4) | `FORWARDED_ALLOW_IPS` env (read by uvicorn) instead of the `CMD` flag | `Dockerfile`, `compose.yaml`, `.env.example`, `scripts/docker_entrypoint.py`, `README.md` | `docker compose config` shows `FORWARDED_ALLOW_IPS: 127.0.0.1`; build BLOCKED |
| D4 | OpenAPI documented 4xx/5xx with a schema the API never returns | Router-level `COMMON_ERROR_RESPONSES` using `ErrorResponse` | `app/api/router.py`, `app/main.py` | new `test_openapi_error_schemas_match_real_envelope` |
| D5 | Dead code / unused error class | Removed `MLModelRepository.list_versions`; DB `IntegrityError` handler uses `ConflictError` | `app/repositories/ml_models.py`, `app/core/error_handlers.py` | full suite, Ruff |

After the fixes: `pytest` → **320 passed, 3 skipped**; Ruff clean; live API audit re-run on a
fresh database → **38 PASS, 0 FAIL**.

---

## 10. Remaining blockers

| # | Blocker | Needed to unblock |
|---|---|---|
| 1 | **No authentication (H1)** | Implement before exposing the service |
| 2 | PostgreSQL migrations and integration tests not run | A **disposable** database URL in `TEST_DATABASE_URL` (commands in §11) |
| 3 | Docker image build and `compose up` not run | Start Docker Desktop, then `docker compose up -d --build` |
| 4 | Real embeddings/classifier not run | Install CPU PyTorch + `requirements-nlp.txt`, `python scripts/download_models.py` (~360 MB) |
| 5 | Real OpenAI call not run (intentionally) | Set `OPENAI_API_KEY`, then `python scripts/smoke_test.py --with-llm` (one small paid call) |
| 6 | Open Medium findings M2 and M3 | Artifact signing; background jobs with time limits |
| 7 | No type checking / CVE scan | Add mypy/pyright config; run `pip-audit` |

---

## 11. Exact commands to run the project locally

**Windows PowerShell (from the project root):**

```powershell
# 1. Environment
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -r requirements-llm.txt          # optional: OpenAI, tiktoken, LangGraph
Copy-Item .env.example .env                  # edit: POSTGRES_PASSWORD, DATABASE_URL, (OPENAI_API_KEY)

# 2. PostgreSQL. Either the Docker dev DB (needs Docker Desktop running) ...
docker compose -f compose.yaml -f compose.dev.yaml up -d db
#    ... with in .env: DATABASE_URL=postgresql+psycopg://aiproject:<POSTGRES_PASSWORD>@127.0.0.1:5433/aiproject
#    ... or your local PostgreSQL 18 with a database and role you created.

# 3. Verify and migrate
python scripts\check_db.py
alembic upgrade head
python scripts\check_config.py --db

# 4. Run
uvicorn app.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs

# 5. Verify (second terminal, venv active)
python scripts\smoke_test.py http://127.0.0.1:8000
python -m pytest -q
ruff check . ; ruff format --check .
$env:TEST_DATABASE_URL = "postgresql+psycopg://<user>:<password>@localhost:5432/<disposable_db>"; python -m pytest -m integration
```

**Full stack in Docker (production-style):**

```bash
cp .env.example .env            # set POSTGRES_PASSWORD (and OPENAI_API_KEY if used)
docker compose up -d --build
docker compose ps               # db and app should be "healthy"
python scripts/smoke_test.py http://127.0.0.1:8000
```

**Linux/macOS:** same as PowerShell, with `python3.12 -m venv .venv && source .venv/bin/activate`
and `cp` instead of `Copy-Item`.
