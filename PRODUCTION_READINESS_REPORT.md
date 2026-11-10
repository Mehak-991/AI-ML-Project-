# Production Readiness Report

AIProject v0.4.0, assessed 2026-11-03.

## Status: READY WITH DOCUMENTED LIMITATIONS

The application was built and verified end to end on a disposable Docker stack. **It has not been
deployed anywhere.** Complete the three blockers below first.

## Phase 21 live deployment (2026-11-11) — completed and verified

Deployed to the local Docker stack `aiproject` (this machine only; not an external host).

| Item | Value |
|---|---|
| Source | commit `c92bbf8` (app, alembic, frontend, compose, Dockerfile identical to `3fe799a`) |
| New images | `aiproject-backend:latest` / `:0.5.0-p21` = `83b37eaeee4a`; `aiproject-frontend:latest` / `:0.5.0-p21` = `3fd9ea8bab02` |
| Previous images (kept) | `aiproject-backend:pre-p21` = `67403b50fc14`; `aiproject-frontend:pre-p21` = `97d04518bf28` |
| Database | PostgreSQL 18 container `aiproject-db-1`, not recreated; volume `aiproject_pgdata` untouched. Revision **0010 -> 0013** |
| Backups | `backups/phase21/aiproject_live_pre_deploy_20261111_004538.dump` SHA-256 `37de9ea2c584b11b58a847d87f44f50b2ab7880c5f2d7624cdfd3e183557dcf5`; `backups/phase21/aiproject_live_quiesced_pre_migration_20261111_005344.dump` (taken with app and worker stopped) SHA-256 `00e7e5f455cefe3b72db778d27c2e1a0bbbaac8c012779de2111a79ea16f990f` |

Sequence: backup, tag old images, build, check fixes inside the image (migrations 0011-0013, `_FeatureCodec`, required-`model_id` check present; all absent from the old image), `compose stop app worker`, quiesced dump, migrate, recreate `app`, `worker`, `frontend` with `--no-deps`.

Deviation: migrations were meant to run one at a time, but the migration container's entrypoint (`RUN_MIGRATIONS=true`) ran `upgrade head` first. Alembic applied 0011, 0012, 0013 in order, with no errors. There is no maintenance-mode feature; the frontend stayed up and the API was unavailable while app and worker were stopped.

### Verification
- Revision 0013; `alembic check` clean; `drift_reports.results` is JSONB with default `'{}'::jsonb`; `ix_jobs_status_created_at`, `ix_datasets_owner_id` and `fk_datasets_owner_id_users` (ON DELETE SET NULL) present; all existing datasets have `owner_id` NULL (legacy, visible to signed-in users); `password_encryption` = scram-sha-256.
- Original data: row counts identical before and after; ID hashes of users, datasets and jobs identical to the pre-migration values; 31 original prediction logs and the "Student Placement Classifier" model still present. That model loads from its original artifact and serves predictions, SHAP and LIME.
- Live end-to-end, 39 of 39 checks passed (script run from the scratchpad): admin self-assignment rejected (403), viewer role by default, wrong password 401, bad token 401, viewer cannot list users, upload or train, refresh rotation with replay detection, logout revokes; upload, `.exe` rejected, train, single and 500-record batch prediction, validation errors, SHAP, LIME (two records), feature importance, prediction history; worker jobs (batch, explainability, drift) completed; a job without `model_id` now ends `failed` with a clear message.
- Services: db, app, worker, frontend healthy, 0 restarts. Worker health check OK. No error logs from the app; the worker's 3 error lines are the jobs described below.
- Behaviour changes from recreating with the current compose: API docs off (`DOCS_ENABLED=false`); `FORWARDED_ALLOW_IPS=172.21.0.10` (nginx fixed address); `/metrics` is no longer reachable through nginx (404) and works only from inside the stack (200, `aiml_worker_health_status 1`); the frontend container's address moved from `.2` to `.10`.

### Side effects to know about
- Two original jobs changed state. `e04d9212` had been stuck in `running` since 2026-10-30 and `dacd114c` was `retry_pending`. The new worker recovered and retried them (`retry_count` 1); both ended `failed` (`requires model_id` and `Prediction input failed validation`). Counts of completed (5) and failed (4) are unchanged from the post-restart snapshot.
- Test data left in the live database: user `p21live_ab8539@example.com` (role `viewer`, was raised to `ml_engineer` by direct SQL for the test and set back), dataset `p21-live-e2e`, model `p21-live-model`, 4 jobs, 5 prediction logs and 1 drift report. Nothing was deleted; removal is up to you.
- The test used a self-registered account because the existing admin's password was not available.

### Rollback readiness
- Preferred: restore either dump into a **new** database (`pg_restore` into a fresh DB), point `DATABASE_URL` at it, and start the `pre-p21` images. The original database is never overwritten. Restoring a dump was rehearsed on an isolated container before this deployment.
- Do not run `alembic downgrade` blindly: 0012's downgrade drops `datasets.owner_id`, and datasets created since now carry an owner.
- Untested: running the `pre-p21` images against the 0013 schema. It is probably compatible (additive column, JSON to JSONB) but was not tried.

### Remaining risks
- `.env` has no `APP_VERSION`, and compose defaults the image tag to `0.4.0`. The stack was deployed with `APP_VERSION=latest`; always pass it (or add it to `.env`), or a plain `docker compose up` will look for a different tag.
- Still open from before: no TLS, database dumps in git history, first registered account becomes admin, rate limits are per process.
- Load tests were run on the p20test stack before this deployment, with the old image. They were not repeated on the new image.

## Phase 21 validation (2026-11-11)

Evidence from this run. Nothing was changed on the live database, the live stack, or `ss_aiml_db`.

### Current baseline
- Backend unit tests: **519 passed, 1 skipped** (optional `langchain_text_splitters`). Earlier figures (430, 495) are out of date.
- `ruff --select=E9,F63,F7,F82` clean. `pip check` clean. `tsc --noEmit` and `vite build` pass.
- `pip-audit -r requirements.txt`: no known vulnerabilities. `npm audit --omit=dev`: 0 vulnerabilities. Trivy was not run (unverified).

### Deployed images are older than the source
Both running stacks use images built before the latest source. Confirmed differences:

| Symptom on the running image | Cause | Source status |
|---|---|---|
| `POST /models/{id}/explainability/lime` returns 500 on a mixed numeric+categorical model | Old image hands strings to LIME's discretizer (`TypeError` in `np.percentile`) | Fixed; regression tests pass |
| A `batch_prediction` job without `model_id` ends `completed` | Old image lacks the required-field check | Fixed (`job_service.py` raises a validation error) |
| Live DB `aiproject-db-1` is at revision **0010**; code head is **0013** | Migrations 0011-0013 never applied to the live DB | Rehearsed below, **not applied** |

The 0.5.0-p20test image contains only 10 migration files. **Rebuild the images and upgrade the database together.**

### Migration rehearsal (isolated)
- Backup of `aiproject-db-1`: `backups/phase21/aiproject_pre0013_20261111_002923.dump` (pg_dump custom format, 42,207 bytes, SHA-256 `b46b6aaa62783313206dc2aced8cc1e1053e94f3b75f485040976b82007244a3`, sidecar `.sha256` verified). The folder is git-ignored.
- Restored into a throwaway container (`p21-rehearsal-db`, `--network none`, no named volumes). Restore: no errors.
- `alembic upgrade` 0010 -> 0011 -> 0012 -> 0013 applied step by step with no errors.
- Row counts and ID checksums for `users`, `datasets`, `jobs` identical before and after.
- 0013 JSON -> JSONB: the live DB has no `drift_reports` rows, so 3 synthetic rows (nested, unicode, null, exponent, duplicate key) were added to the **rehearsal copy only**. Checksum identical after the cast; default became `'{}'::jsonb`.
- `ix_jobs_status_created_at` (partial, queued/running/retry_pending), `ix_datasets_owner_id` and `fk_datasets_owner_id_users` exist. `datasets.owner_id` is NULL for existing rows (legacy, visible to all signed-in users).
- `alembic check`: no drift between models and schema.
- Downgrade 0013 -> 0010 then upgrade again: works, JSON type restored then JSONB again, seeded rows preserved.
- All 11 ORM models query cleanly against the migrated schema.
- Limits of this rehearsal: the live data is tiny (1 user, 1 dataset, 9 jobs), so lock time and timing on large tables are not measured.

### Rollback plan for the live upgrade (not yet executed)
1. Take a fresh `pg_dump` immediately before upgrading and verify its SHA-256. Tag the current images: `docker tag aiproject-backend:latest aiproject-backend:pre-p21`.
2. Stop `app` and `worker` first so nothing writes during the upgrade.
3. Upgrade failed or wrong: `alembic downgrade 0010` (rehearsed, preserves data). Downgrading 0012 drops `datasets.owner_id`, so any ownership assigned after the upgrade is lost.
4. Downgrade impossible: restore the dump into a **new** database and point `DATABASE_URL` at it. Do not overwrite the live database.
5. Restart the old image tag.

### Isolation of the p20test stack
Separate compose project, networks (`aiproject-p20test_*`), named volumes and database from the live stack. Row counts differ (3 users / 42 jobs against 1 user / 9 jobs). Published port 8089 only. All load tests went to `localhost:8089`; nothing touched the live stack.

### RBAC and authorization (observed on p20test)
- Registration with `role: admin` returns 403. Plain registration yields `viewer`.
- Viewer: reads succeed, `GET /auth/users` returns 403, prediction on another user's model returns 403.
- An `ml_engineer` also gets 403 on a model it does not own (object-level authorization).
- Test shortcut: the throwaway load-test user was set to `ml_engineer` directly in the p20test DB because the API offers no self-promotion.

### ML and worker (real artifacts, p20test)
- CSV upload, then training of a model (0.6 s, accuracy 0.979 on its train split), then prediction. Single prediction 89 ms; batch of 100 in 76 ms; batch of 1,000 in 121 ms (about 8,300 records/s). Bad or missing features get a clear 422.
- Uploads: `.exe` rejected (415), empty file rejected (400), filename `../../etc/x.csv` stored as `x.csv`.
- SHAP and feature importance return 200. LIME returns 500 on the old image (see above); source tests pass.
- Worker health check reads real heartbeat age (healthy at 0.5 s old; fails when the threshold is exceeded). The heartbeat is written by the main poll loop, so a hung loop shows as unhealthy.
- Jobs: `batch_prediction` with 50 records completed with real predictions; `explainability` completed; a job with no records failed with a clear message. SIGKILL recovery was not re-run in this phase; it rests on the earlier Phase 20 result and unit tests.

### Load test (p20test only, 20 s per level, bounded, no aborts)
Mixed GET traffic (`/health`, `/auth/me`, `/models`, `/datasets`):

| Users | req/s | errors | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 1 | 66 | 0 | 15 ms | 20 ms | 24 ms |
| 10 | 131 | 0 | 73 ms | 120 ms | 146 ms |
| 50 | 117 | 0 | 357 ms | 543 ms | 1,231 ms |
| 100 | 89 | 0 | 620 ms | 3,323 ms | 5,937 ms |

Same mix plus single prediction and 100-record batch prediction:

| Users | req/s | errors | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 1 | 24 | 0 | 18 ms | 114 ms | 129 ms |
| 10 | 60 | 0 | 136 ms | 346 ms | 456 ms |
| 50 | 59 | 0 | 711 ms | 1,303 ms | 1,536 ms |

Throughput peaks near 10 users and then flattens. Mid-run, the app container used about 175% CPU and the database about 29% CPU, so the 2-worker API is CPU-bound. At 100 users tail latency degrades (p95 3.3 s) but with zero errors. The tool was a custom asyncio/httpx script (Locust is not installed), run from the same machine as the containers, so numbers include client overhead. Database connections stayed at 20 of 100. Memory stayed near 435 MiB for the app.
Not measured: prediction-only load at 100 users, queue latency under load, long runs.

### Remaining actions before go-live
1. Your approval to rebuild images and upgrade the live database (plan above).
2. Re-run the e2e checks above on the rebuilt images.
3. The three blockers listed below.

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
| Backend tests pass | Met | 519 passed, 1 skipped (optional package), re-run 2026-11-11 |
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
