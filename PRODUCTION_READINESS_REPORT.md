# Production Readiness Report

AIProject v0.4.0, assessed 2026-11-03.

## Status: READY WITH DOCUMENTED LIMITATIONS

The application was built and verified end to end on a disposable Docker stack. **It has not been
deployed anywhere.** Complete the three blockers below first.

## Before going live

| # | Blocker | Action |
|---|---|---|
| 1 | Database dumps remain in git history on GitHub | Change the exposed account's password. If the repository is or was public, rewrite history (`git filter-repo --path backups --invert-paths`) and force-push. See SECURITY_AUDIT_REPORT.md |
| 2 | No TLS | Put a TLS terminator in front, including the Nginx real-IP settings in DEPLOYMENT_GUIDE.md |
| 3 | First registered account becomes admin | Register your admin before the service is reachable by others |

## Required on your local setup

The code now expects migrations `0012` and `0013`. Your local database `ss_aiml_db` is still at `0011`,
deliberately untouched, so **the local API returns errors on dataset queries until you run**:

```powershell
.\.venv312\Scripts\python.exe -m alembic upgrade head
```

Both migrations keep all data: one adds a nullable column and index, the other changes a column from
JSON to JSONB with a value-preserving cast. Your 4 existing datasets get no owner, so every signed-in
user can still see them.

## Scorecard

| Criterion | Status | Evidence |
|---|---|---|
| No known unresolved critical or high bugs in the code | Met | BUG_FIX_REPORT.md. History exposure is blocker 1 |
| Backend tests pass | Met | 495 passed, 1 skipped (optional package) |
| Frontend production build | Met | `npm ci`, `tsc`, `vite build` |
| Ruff | Met | Requested rules and CI's security rules |
| Python dependency checks | Met | `pip check`, `pip-audit` |
| Authentication and authorization | Met | 62-check end-to-end run, 52 regression tests |
| Migrations consistent | Met | Single head; `alembic check` clean on PostgreSQL 18; reversible |
| ML training and prediction | Met | Both trainers, classification and regression, end to end |
| Explainability | Met | 18 of 18 combinations; was mostly failing |
| Workers process and recover jobs | Met | Real `SIGKILL` recovery on Docker |
| Docker services build and become healthy | Met | Hardened compose stack |
| Data survives restarts | Met | Full down and up on real volumes |
| No secrets exposed | **Partly** | Logs clean, secrets required at startup. Blocker 1 remains in git history |
| Deployment instructions complete | Met | DEPLOYMENT_GUIDE.md, ENVIRONMENT_SETUP.md |
| Monitoring and health checks | Met, basic | Health checks, JSON logs, Prometheus endpoint. No Prometheus or Grafana bundled |
| TLS | **Not met** | External by design; blocker 2 |
| Performance under load | **Unknown** | Single-client latency only |
| Real production deployment | **Not done** | Needs your approval |

## Behaviour changes to know about

Necessary for security, but they can affect existing clients:

- Anonymous calls to `/deployments`, `/drift/*` and `/datasets/validate` now return 401.
- `/datasets/validate` needs the admin or ml_engineer role.
- Non-admins see only their own datasets, experiments, deployments and drift data, plus objects with no
  owner. Viewers can't upload or train, so they see only ownerless objects. Decide whether that fits how you want viewers to work.
- Replaying a used refresh token signs that user out everywhere.
- `APP_ENV=production` refuses a weak JWT secret or `DATABASE_ECHO=true`.
- In Compose, `/docs` and `/openapi.json` are off by default, and the API no longer runs jobs itself.
- Ground truth must have one label per predicted record.
- Jobs without their required `model_id` or `experiment_id` now end `failed`, not `completed`.
- Explanation responses gain an optional `explained_class` field. `target_class` now works.

## Known limitations

| Limitation | Impact | When to act |
|---|---|---|
| Single host | No failover | If uptime needs exceed one machine |
| Rate limits per process | Effective limit up to 2× with 2 API processes | When strict limits matter; use a gateway limiter |
| Training and AutoML through direct endpoints run in the request | Long runs hit Nginx's 300 s limit | Use `POST /jobs` for big datasets |
| Cancelling a running job doesn't stop its computation | Worker slot busy until it finishes | Rarely matters; result is discarded |
| Worker stopped mid-job waits for the stale timeout (default 15 min) | Delay before retry | Tune `JOB_STALE_TIMEOUT_MINUTES` |
| Drift overview runs several queries per model | Slower with hundreds of models | Measure when model count grows |
| No delete endpoints | Data only grows; expired refresh tokens too | Add retention when needed |
| No way to assign an owner to legacy objects via API | Existing datasets stay visible to all signed-in users | SQL for now, or add an endpoint |
| Monitoring overview counts are platform-wide | Counts only, no details | If counts are sensitive |
| Tokens in `sessionStorage` | New tabs need a new login; XSS would expose them (CSP reduces this) | Consider httpOnly cookies later |
| joblib artifacts are pickles | Write access to `MODEL_DIR` plus the database means code execution | Protect both |
| Older reports FINAL_AUDIT_REPORT.md, DOCKER_VERIFICATION_REPORT.md | Outdated | Kept as history; delete if you prefer |

## Recommended next steps

1. Resolve the three blockers, then migrate the local database.
2. Choose hosting and a domain. Everything external waits for your approval.
3. Schedule `scripts/backup_db.py` plus volume archives, copied off the host. No schedule exists yet.
4. Run a bounded load test on the target machine to size processes, pool and memory.
5. Add Prometheus and alerts on `aiml_worker_health_status`, failed jobs and 5xx rates.
6. Decide what viewers should see.
