# Bug Fix Report

Audit of AIProject v0.4.0, starting from commit `3f695cc`, on 2026-11-03. Every bug below was
confirmed by reading the code and, where noted, reproducing it. Regression tests are in
[tests/unit/test_production_readiness.py](tests/unit/test_production_readiness.py) unless stated.

## Critical

| # | Bug | Effect | Fix | Files |
|---|---|---|---|---|
| 1 | No authentication on `GET /deployments`, `GET /deployments/{id}`, all `GET /drift/*`, and `POST /datasets/validate` | Anyone could read deployment and drift data, or make the server parse 25 MB uploads, without logging in | Login required; validate needs admin or ml_engineer | `app/api/routes/deployments.py`, `drift.py`, `datasets.py` |
| 2 | Production started with the public default JWT secret or a short one, and `.env.example` shipped that default | Anyone could forge an admin token | Production refuses to start; `.env.example` is blank | `app/core/config.py`, `app/main.py`, `.env.example` |
| 3 | Database backups were committed and pushed to GitHub | Emails, password hashes and refresh-token hashes in the repository | Untracked; files kept locally. **History still contains them: see Remaining actions** | `backups/` |

## High

| # | Bug | Effect | Fix | Files |
|---|---|---|---|---|
| 4 | Missing ownership checks: datasets (no owner existed), experiments (read, run, rerun, cancel, compare), deployments, drift data, model monitoring, explainability summary, jobs linked to another user's experiment or dataset, training on another user's dataset | Any signed-in user could read or act on other users' objects | Ownership checks and scoped listings; additive migration `0012` adds `datasets.owner_id` | `app/services/authorization.py`, routes, repositories |
| 5 | Local SHAP failed for 5 of 6 tested model/data combinations; local LIME failed for all 6 | 500 errors for any model with a categorical feature (and LIME for numeric-only too) | Explanations run over an all-numeric encoding decoded back to real features; verified across binary, multiclass and regression, linear and random forest | `app/services/explainability_service.py` |
| 6 | Global importance silently fell back for models with categorical features, and the fallback looked up the wrong pipeline step, returning equal weights | Plausible-looking but meaningless importance scores | Uses SHAP; the fallback now reads the real estimator and sums one-hot columns per feature | same |
| 7 | `execute_pipeline_run` didn't roll back before recording a failure | A failed flush raised a second error: API 500 and the experiment stuck in `running` forever | Rollback first, then record the failure; orphaned artifact deleted | `app/services/experiment_service.py` |
| 8 | Experiment training skipped the preprocessing used for prediction | Mixed-type columns failed or predicted inconsistently; duplicate rows could land in both train and test | Shares `select_features`, de-duplication, `coerce_features`, stratified split and the preprocessor with normal training | same |
| 9 | Failed experiment run reported its job as `completed`; a job missing its `model_id` or `experiment_id` ran a placeholder and reported `success` | False success, with no work done | Both now fail with a clear message | `app/services/job_service.py` |
| 10 | Failure text was written unbounded to `jobs.current_stage` (VARCHAR 128) | On PostgreSQL the write itself failed, leaving the job `running` until the reaper. SQLite tests can't see this | Truncated to the column size | same |
| 11 | Database errors during token validation returned 401 | A database outage looked like an invalid token and signed users out | Errors outside token parsing propagate as 503 | `app/api/deps.py` |
| 12 | Concurrent refresh requests with one token could all succeed; replaying a rotated token had no consequence | Stolen tokens stayed usable | Atomic rotation; a replay revokes all of the user's sessions | `app/services/auth_service.py` |
| 13 | Compose let `FORWARDED_ALLOW_IPS=127.0.0.1` from `.env` override the Nginx address | All users shared one IP: one login rate-limit budget, and audit logs without client addresses | Compose always trusts its own Nginx | `compose.yaml` |
| 14 | Nginx default 60 s timeout, while training, AutoML and Ollama (up to 180 s) run in the request | Slow but working requests returned 504 | 300 s for `/api/` | `frontend/nginx.conf` |
| 15 | Restore script could deadlock on any non-trivial dump (unread stdout pipe), reported success when SQL statements failed (no `ON_ERROR_STOP`), and interpolated the database name into SQL | A restore could hang, or silently produce a partial database | All three fixed | `scripts/restore_db.py` |
| 16 | Frontend kept showing a signed-in UI after the session ended, and any failure of `/auth/me`, including an outage, deleted the tokens | Pages full of 401s; outages signed users out | Session-expired event returns to the sign-in screen; only 401/403 clear tokens | `frontend/src/services/api.ts`, `context/AuthContext.tsx` |
| 17 | Opening the deployment page ran a real prediction for the selected model | Fake rows in the audit history and inflated prediction metrics | The probe only runs when clicked | `frontend/src/pages/DeploymentMonitoringPage.tsx` |

## Medium

| # | Bug | Fix | Files |
|---|---|---|---|
| 18 | API ran submitted jobs in its own thread pool, racing the worker and normally winning, so ML load stayed in the API container | `JOB_INLINE_DISPATCH`; compose sets false. Verified: API ran 0 jobs, worker ran all | `job_service.py`, `routes/jobs.py`, `compose.yaml` |
| 19 | Every authenticated request held two pooled database connections for its whole duration | Auth lookup releases its connection immediately | `app/api/deps.py` |
| 20 | Prediction re-read and hashed the whole artifact per request (measured 43–111 ms for a 25 MB forest), though the model was already cached | Hash once per file version, still before any unpickling | `app/ml/persistence.py` |
| 21 | `aiml_worker_health_status` was always 0 in Docker: API read a heartbeat file on the worker's private tmpfs | Heartbeat on the shared volume, path configurable. Verified 1 | `compose.yaml`, `app/core/metrics.py`, `scripts/run_worker.py` |
| 22 | Permanent errors (`TrainingError`, invalid job config, 4xx in general) were retried pointlessly | Client errors fail immediately | `job_service.py` |
| 23 | Manual job retry kept the old `completed_at`, `started_at`, `result` and duration | Cleared on retry | same |
| 24 | Two runs of the same experiment could execute at once; a cancel during training was overwritten by `completed` and a model was still registered | Row lock with 409; orphaned runs replaced after the stale timeout; cancel wins | `experiment_service.py` |
| 25 | `validation_size=0` always failed; impossible split sizes and huge hyperparameter grids were accepted | Handled, and validated at creation (limit: 100 candidates) | `experiment_service.py`, `schemas/experiment.py` |
| 26 | Expensive routes (`POST /jobs`, experiment run/rerun, SHAP/LIME, drift analysis) had only the default 300/min limit | Experiment runs share the training budget (10/min); the rest get an analysis budget (60/min) | `app/core/middleware.py` |
| 27 | Login accepted unbounded passwords, which raised 500 past passlib's limit | Max length, returns 422 | `app/schemas/auth.py` |
| 28 | Login response time revealed whether an email exists | Same hashing work for unknown emails | `app/core/security.py`, `auth_service.py` |
| 29 | Tokens without `exp` or `sub`, or of another type, were accepted if signed; `JWT_ALGORITHM` took any value | Required claims, type check, HMAC-only allowlist | `security.py`, `config.py` |
| 30 | Ground truth of the wrong length was accepted and scored the wrong rows; regression models got a meaningless "accuracy" | 422 on mismatch; accuracy only for classification | `deployment_service.py` |
| 31 | `.env` value `OLLAMA_BASE_URL=127.0.0.1` broke LLM calls in containers | Compose uses `host.docker.internal` | `compose.yaml` |
| 32 | Worker and migration got `JWT_SECRET_KEY` only via an optional env file; `.env.example` lacked newer settings | Explicit and required; example completed | `compose.yaml`, `.env.example` |
| 33 | `alembic check` failed on PostgreSQL: `drift_reports.results` was JSON, the model says JSONB | Additive migration `0013` (value-preserving cast) | `alembic/versions/` |
| 34 | SPA static location lost all security headers; `index.html` had no cache policy; favicon cached as immutable | Shared header file, `/assets/` immutable, `index.html` revalidates, CSP added | `frontend/nginx.conf`, `security-headers.inc` |
| 35 | Nginx cached the API's IP at startup and failed if `app` was down when it started | Resolved at request time | `frontend/nginx.conf` |
| 36 | Refresh call hardcoded `/api/v1`, ignoring `VITE_API_BASE_URL` | Uses the client's base URL | `frontend/src/services/api.ts` |
| 37 | 973 kB initial JavaScript | Route-level code splitting: 318 kB (102 kB gzip) | `frontend/src/App.tsx` |
| 38 | Signed-out users saw broken pages with raw 401 errors | Sign-in screen | same |
| 39 | Dependency versions drifted between builds; `pyproject.toml` lacked 7 runtime dependencies | `requirements.lock` from the verified image; pyproject synced | `requirements.lock`, `Dockerfile`, `pyproject.toml` |
| 40 | CI never ran against PostgreSQL, so bugs 10 and 33 couldn't be caught | PostgreSQL service and integration tests in CI; compose validation | `.github/workflows/ci.yml` |
| 47 | `app`, `worker` and `migration` built one image tag with different build args, so `INSTALL_LLM=true` could silently lose its packages from the API's image | One shared build definition | `compose.yaml` |

## Low

| # | Bug | Fix |
|---|---|---|
| 41 | Worker ignored `LOG_FORMAT=json` | Uses the shared logging setup |
| 42 | `DATABASE_ECHO=true` allowed in production, logging SQL parameters | Refused at startup |
| 43 | Long auto-generated model names could exceed the 255-character column | Truncated |
| 44 | `scripts/smoke_test.py` had been broken since authentication was added | Takes credentials from the environment |
| 45 | README claimed "no authentication", Postgres 17 and a port-8000 deployment | Corrected |
| 46 | A deployment-guide rollback check used `/health`, which Nginx answers with the SPA | Uses `/api/v1/health` |

## Tests changed

Existing tests were changed only where they encoded the old behaviour:

- `test_weak_jwt_secret_flagged_in_production` is now `test_weak_jwt_secret_refused_in_production`:
  it asserts the stricter behaviour you asked for in section 10.
- `tests/unit/test_config.py` and `test_endpoints.py` production fixtures now supply a strong secret.
- `test_uploads_get_the_larger_upload_limit` now authenticates, because the endpoint requires it.
  What it asserts is unchanged.
- `tests/integration/test_database.py::test_api_workflow_against_postgres` shared one connection
  between requests, which failed on the original commit too. It now uses separate connections and
  real commits in a throwaway schema, the way production behaves.

No test was skipped or removed.

## Remaining actions

See [PRODUCTION_READINESS_REPORT.md](PRODUCTION_READINESS_REPORT.md). The two you need to do yourself
are removing the backups from git history and running `alembic upgrade head` on your local database.
