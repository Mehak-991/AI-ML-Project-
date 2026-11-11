# Production Readiness

**Verdict: the application is ready for a controlled production rollout of RBAC v2 and for a
college demonstration. It is not yet ready for public internet exposure**, because of the blockers in
section 3. Every box below links to its evidence; unchecked means not done or not provable here.

## 1. Acceptance checklist

| ☐/☑ | Criterion | Evidence |
|---|---|---|
| ☑ | Existing architecture preserved | Same layers/modules; only additive changes plus the RBAC v2 work already merged |
| ☑ | Backend starts | Health `ok` on the disposable stack (`DEPLOYMENT_REPORT.md`) |
| ☑ | Frontend builds | `npm run build` passes; served by Nginx (HTTP 200) |
| ☑ | Database connectivity | `/api/v1/health` reports database `ok` |
| ☑ | Alembic chain verified | 14 revisions apply to an empty PostgreSQL 18; guarded downgrade and abort conditions tested; rehearsal on a restored backup copy (earlier phase) |
| ☑ | Authentication works | E2E: login, refresh rotation, replay rejection, logout and password-change revocation |
| ☑ | RBAC v2 works | `test_rbac_matrix.py` (every route × role) and E2E |
| ☑ | User/admin/superadmin permissions verified | Matrix tests and E2E |
| ☑ | Audit logging works | E2E (role change, deactivation recorded, no password material); triggers block edits (integration tests) |
| ☑ | Dataset management | Upload, validate, preview, profile — unit and E2E |
| ☑ | Model training | Four algorithms, E2E |
| ☑ | Model evaluation | Train/validation/test, baseline, cross-validation, confusion matrix |
| ☑ | Prediction | Single, batch, history — E2E |
| ☑ | SHAP / LIME | E2E |
| ☑ | Background jobs | E2E batch and training jobs through the worker; concurrency tests on PostgreSQL |
| ☑ | Docker services healthy | db, app, worker, frontend healthy on the disposable stack |
| ☑ | Nginx routing | `/` → SPA, `/api/*` → API, `/metrics` and docs blocked |
| ☑ | Persistent storage | Counts and artifact files identical after restart |
| ☑ | Automated tests pass | `FINAL_TEST_REPORT.md` |
| ☑ | Security checks completed | `SECURITY_AUDIT.md` |
| ◐ | CI/CD validated | Pipeline updated and each step reproduced locally; hosted run result not readable here |
| ☑ | College report, slides, viva material | `docs/college-submission/` (screenshots must be taken by hand) |
| ☑ | Deployment guide, backup/restore, migration, rollback documented | `DEPLOYMENT_GUIDE.md`, `reports/DEPLOYMENT_REPORT.md`, `docs/LOCAL_DEVELOPMENT.md` |
| ☑ | Blockers identified | section 3 |
| ☐ | Production running RBAC v2 | **No.** Production is on `0.5.0-p21` / revision `0013` |
| ☐ | Public HTTPS | **No.** Needs a domain and certificate |

## 2. Operational readiness

| Area | State |
|---|---|
| Health checks | `/api/v1/health` (liveness + database), container health checks for all four services, `scripts/check_stack.py` |
| Logging | Structured JSON logs with request IDs; no credentials in log messages |
| Monitoring | Opt-in Prometheus overlay (`compose.monitoring.yaml`), token-protected metrics, not public |
| Resource limits | `read_only` filesystems, `cap_drop`, tmpfs sizes; CPU/memory limits are not set in Compose (add per host) |
| Backups | `scripts/backup_db.py` (checksummed, retention) and `scripts/restore_db.py` (isolated target, dry run). **No backup schedule is configured**; schedule it with the host's task scheduler. Restore is proven at gate G3 |
| Rate limiting | Per-bucket limits in the API |
| Security headers | Present at the edge; HSTS only with the TLS overlay |
| Admin account setup | Server-side `scripts/create_superadmin.py`; recovery with `scripts/reset_password.py` |
| Incident recovery | Restore the verified backup into a new database (`DEPLOYMENT_REPORT.md` section 4) |

## 3. Production blockers (in order)

1. **Admin password rotation not confirmed** and Git history still contains the exposed backups.
2. **Owner approvals** for the rollout gates G1–G9 (`DEPLOYMENT_REPORT.md`), including the choice of
   the superadmin account.
3. **Final images must be rebuilt** from the merged commit and re-verified (the `rc2` build predates
   the last commits).
4. **Domain, DNS and TLS certificate** for public access; set `DOCS_ENABLED=false`, keep metrics
   internal.
5. **Backup schedule** and a tested restore on the real host.
6. Recommended before wide public use: a reduced-privilege runtime database role, a self-service
   password-reset flow, frontend component tests.

## 4. Decisions taken (safest reasonable defaults)

* `E501` (line length) is advisory; every other Ruff rule, including security rules, is enforced and
  now runs in CI.
* New algorithms: gradient boosting and decision tree were added to the same pipeline; no new
  libraries.
* Cross-validation runs on training+validation rows only and is skipped (with a stated reason) for
  more than 20,000 training rows or too-small classes, to bound training time.
* The `reports/` folder is now tracked (it was in `.gitignore`).
* `docker-build.log` was untracked (kept on disk, ignored).
* Password reset by email and a superadmin-set password were **not** added: they need an email
  service or a product decision; operator CLI recovery exists.
