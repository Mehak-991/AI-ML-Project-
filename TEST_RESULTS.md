# Test Results

Final run on 2026-11-03: Windows 11, Python 3.12, Node 22, PostgreSQL 18.6, Docker 29.6.2. Everything
below ran against the final code unless noted. The original commit's baseline was 443 passed, 1 skipped.

## Automated checks

| Check | Command | Result |
|---|---|---|
| Unit and API tests | `pytest tests/unit/ -v --tb=short` | **495 passed, 1 skipped** |
| Lint (requested rules) | `ruff check . --select=E9,F63,F7,F82` | Pass |
| Lint with security rules (CI's rule set) | `ruff check . --select=E9,F63,F7,F82,S` | Pass |
| Dependencies | `pip check` | No broken requirements |
| Frontend install | `npm ci` | Pass |
| Frontend types and build | `npm run build` (`tsc -b && vite build`) | Pass |
| Python vulnerabilities | `pip-audit` on the 69 versions in `requirements.lock` | None known |
| npm vulnerabilities | `npm audit --audit-level=high` | 0 |
| PostgreSQL integration tests | `pytest tests/integration`, disposable database | **10 passed** |
| Migrations | upgrade to `0013` from empty, `alembic check`, downgrade to `0011`, upgrade | Pass; single head; no schema drift |

The skipped test needs the optional `langchain_text_splitters` package, which this environment doesn't
install. It was skipped in the baseline too.

**Do the regression tests detect the bugs?** The new test file, run against the original commit's
code: 50 of 52 fail. The 2 that pass there guard behaviour that was already correct.

The original commit also failed `alembic check` and 1 integration test when run on PostgreSQL. CI
hadn't run them against PostgreSQL, so neither failure was visible.

## Docker stack

A separate Compose project (`aiproject-verify`) on its own port, network and volumes, built with the
documented workflow and removed afterwards. Your existing stacks and volumes weren't touched.

| Check | Result |
|---|---|
| Image builds from `requirements.lock` | Pass |
| `up --wait` | `db`, `app`, `worker`, `frontend` healthy; `migration` exited 0; revision 0013 |
| `scripts/e2e_check.py` through Nginx | **62 passed, 0 failed** |
| Jobs executed by | Worker 3, API 0 |
| `SIGKILL` the worker during training (run with a 1-minute stale timeout) | Job re-queued, then completed; `retry_count` 1 |
| Full `down` and `up`, keeping volumes | Same model and dataset counts; login works; persisted artifact predicts |
| Backup, checksum and restore into a new database | Row counts and revision identical (4 users, 1 dataset, 3 models, 3 jobs, 6 prediction logs) |
| Upload and model volumes readable for archiving | Pass |
| Passwords, JWT secret and tokens in logs of all 5 containers | 0 matches |
| Start with a weak JWT secret | Refused, with a clear message |
| Compose without `JWT_SECRET_KEY` | Refused |
| `/metrics` through Nginx | Not exposed |
| `/metrics` inside the network | `aiml_worker_health_status 1` |
| LLM through Nginx, API and host Ollama (`llama3.2:3b`) | 200 in 8.8 s |
| API sees client IP | Not Nginx's: proxy trust works |
| Non-root, read-only filesystem, capabilities | See SECURITY_AUDIT_REPORT.md |

`e2e_check.py` covers: login, registration, token refresh and replay, roles, ownership denial, dataset
upload, validation and rejection, training, listing, single and batch prediction, job submission and
monitoring, prediction history, ground truth, experiments with grid search, SHAP, LIME, global
importance, deployment and undeployment, monitoring, all three drift analyses, and user listing.

## Browser

Headless Microsoft Edge against the Nginx-served production build: 15 of 15 checks passed, with no
console errors, page errors, CSP violations or 5xx responses.

Checked: signed-out screen, login through the real form, all 9 pages render with data, session survives
a reload, a rejected session returns to sign-in, no horizontal scroll at 390 px.

This pass opens pages. It doesn't click through every form; those flows are covered at API level by
`e2e_check.py`. The browser script itself isn't part of the repository.

## Explainability

Before the fix, across 6 model and data combinations: local SHAP failed 5, local LIME failed 6, and
global importance silently used the fallback on 5. After: all 18 succeed. A test also checks SHAP's
defining property on real output: base value plus contributions equals the prediction.

## Measured latency

Through Nginx to the Docker stack on this development laptop. 20–40 sequential requests per row, paced
below the rate limit. Not a load test, and no concurrent load was applied.

| Operation | p50 | p95 |
|---|---|---|
| Predict 1 row, linear | 35.7 ms | 69.9 ms |
| Predict 1 row, random forest with 25 MB artifact | 61.2 ms | 85.5 ms |
| Predict 1000 rows, same forest | 81.0 ms | 103.1 ms |
| `GET /auth/me` | 10.6 ms | 12.0 ms |
| `GET /models` | 16.2 ms | 19.8 ms |
| `GET /predictions/history` | 16.5 ms | 20.1 ms |
| `GET /jobs/metrics` | 13.6 ms | 15.4 ms |
| `GET /monitoring/overview` | 21.6 ms | 27.6 ms |
| `GET /drift/overview` (few models; grows with model count) | 47.3 ms | 66.4 ms |
| `GET /api/v1/health` | 8.7 ms | 9.7 ms |

Single runs: train random forest on 40,000 rows 10.5 s; train linear 1.2 s; local SHAP 802 ms; local LIME
197 ms; global importance 1644 ms.

Effect of the fixes:

| Change | Before | After |
|---|---|---|
| Artifact hashing per prediction, 25 MB file | 43–111 ms measured | Once per file version |
| Predict 1 row, same forest (earlier run was unpaced, so only a rough comparison) | 199 ms | 61 ms |
| Initial JavaScript | 973 kB (261 kB gzip) | 317 kB (102 kB gzip) |
| Pooled connections held per authenticated request | 2 | 1 |

## Not tested

| Item | Why |
|---|---|
| Real production deployment, TLS, DNS | Needs your approval and infrastructure |
| OpenAI provider against the real service | Paid; uses in-memory transport in tests |
| Embeddings and classification with real models | Optional PyTorch packages not installed; fakes only |
| LangGraph analysis workflow | Optional package not installed |
| Load, sustained concurrency, memory under pressure | Unbounded stress tests were out of scope |
| Migrating your real local database | Left for you; see PRODUCTION_READINESS_REPORT.md |
| Multiple simultaneous workers on the Docker stack | Claiming is covered by PostgreSQL concurrency tests only |
| Prometheus scraping with a real server | `/metrics` output and token checked directly |
