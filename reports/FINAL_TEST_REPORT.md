# Final Test Report

**Branch:** `chore/final-completion` (based on `main` at `76012ee`, the merge of PR #1)
**Verified commit:** `d3d8fe0` (later commits only add documentation)
**Run date:** 2026-11-11, on a developer workstation (Windows 11, Docker Desktop, Python 3.12, Node 22)
**Environment:** isolated only. Nothing below touched the production database, containers or volumes.

Raw run summary (the output of the script below, no secrets in it) is reproduced under "Evidence".

## 1. Results

| Suite | Command | Total | Passed | Failed | Skipped |
|---|---|---:|---:|---:|---:|
| Backend unit (SQLite test double, CI environment variables) | `APP_ENV=testing DOCS_ENABLED=true RATE_LIMIT_ENABLED=false pytest tests/unit -q` | 744 | **743** | 0 | 1 |
| PostgreSQL integration (empty PostgreSQL 18, `alembic upgrade head` first) | `TEST_DATABASE_URL=… pytest tests/integration -q` | 36 | **36** | 0 | 0 |
| Full-stack end-to-end (disposable Docker stack, release-candidate images `0.6.0-rc2`) | `python scripts/e2e_check.py --base-url http://127.0.0.1:18099 --confirm-disposable` | 97 | **97** | 0 | 0 |
| Stack smoke check | `python scripts/check_stack.py --origin http://127.0.0.1:18099` | — | PASSED (0 failures; 1 informational warning) | 0 | — |

The one skipped unit test is environment-conditional (`tests/unit/ai/test_runtime_cache.py`, it skips
when an optional Hugging Face package is present). The two build-dependent frontend consistency tests
ran, because the production build existed.

### Static analysis, dependency and secret checks

| Check | Command | Result |
|---|---|---|
| Ruff (full project rule set, incl. bandit `S`) | `ruff check .` | All checks passed |
| Python dependency consistency | `pip check` | No broken requirements |
| Python dependency vulnerabilities | `pip-audit -r requirements.lock --no-deps --disable-pip` | No known vulnerabilities |
| Secret scan, whole Git history | gitleaks v8.30.0, same command and `.gitleaks.toml` as CI | No leaks found |
| Forbidden tracked files | `python scripts/check_tracked_files.py` | None |
| Compose validation | `docker compose -f compose.yaml config --quiet` | Valid with `APP_VERSION`; fails without it, as designed |
| Frontend dependency audit | `npm audit --audit-level=high` | 0 vulnerabilities |
| Frontend type check + production build | `npm run build` (`tsc -b && vite build`) | Passes |
| Frontend lint | `npm run lint` (oxlint) | Exit 0; 23 warnings (see limitations) |

## 2. What the tests cover

* **Access control:** `test_rbac_matrix.py` drives every route as anonymous, user, admin and
  superadmin, checks forged/unsigned tokens, that the role claim inside a token is ignored, and that a
  route without a declared policy is refused.
* **Accounts and roles:** registration always creates a `user`; role changes; last-superadmin
  protection; deactivation; guarded delete; audit entries; CLI bootstrap/recovery safeguards.
* **Concurrency on real PostgreSQL:** simultaneous demotions of the last superadmins, a ring of five,
  concurrent deactivations, simultaneous bootstrap and registrations.
* **Migrations:** every revision applied to an empty database (14 migrations to `0014`); upgrade,
  guarded downgrade, abort on an unmapped legacy role, and a rehearsal on a restored backup copy
  (earlier phase, see `RBAC_V2_IMPLEMENTATION_REPORT.md`).
* **Audit log:** same-transaction writes; UPDATE/DELETE/TRUNCATE rejected by database triggers.
* **ML:** training for four algorithms (classification and regression), baseline and test metrics,
  cross-validation (including the "class too small" and "too large" skips), artifact save/load
  round-trip and tamper detection, prediction validation, explainability, experiments running the
  algorithm that was requested.
* **Data:** upload validation, wrong file type, size limits, dataset preview bounds and null-safety.
* **Operations:** health/readiness, rate limiting, request limits, job claiming and recovery,
  deployment hardening, Docker/compose static guards, frontend/backend consistency guards.
* **End-to-end (97 checks):** registration, login, refresh rotation and replay rejection, upload,
  validation, preview, training (four algorithms), cross-validation, prediction, ground truth, batch
  and training jobs through the worker, experiments, SHAP/LIME, deploy/undeploy, drift/quality/
  performance reports, ownership isolation, profile update, privilege-escalation attempts, password
  change (old password and tokens stop working), logout revocation, role change, deactivation, audit
  log content (no password material).

## 3. Defects found by testing during this phase

| Found by | Defect | Resolution |
|---|---|---|
| New unit test for rare classes | Cross-validation built its splitter before checking the fold count, so a class with one row raised `ValueError` | Fold count validated first; returns "skipped" with a reason. Test added |
| New experiment test | Experiments store no estimator name in model metadata, so the algorithm that actually ran could not be verified | `estimator` recorded; test asserts the requested algorithm is the one trained |
| CI reproduction (PR #1) | Rate-limit tests failed under CI's job-level environment variables; integration tests assumed a migrated schema | Test isolation clears the variables; CI runs `alembic upgrade head` first |

## 4. Known limitations (not hidden)

* **Frontend has no component/unit test runner.** It is covered by type-checking, the production
  build, static consistency tests (`test_frontend_*.py`) and the end-to-end run. Adding Vitest +
  Testing Library is recommended future work.
* **Frontend lint:** 23 oxlint warnings remain (React `set-state-in-effect` fetch-on-mount patterns,
  four `exhaustive-deps`). They are warnings, not errors, and were not changed in this phase to avoid
  behavioural regressions without UI tests.
* **No browser-driven UI test.** The UI was not exercised with a real browser here; screenshots must
  be captured by hand (`docs/college-submission/06-screenshot-checklist.md`).
* **The end-to-end run used a disposable stack**, with the auth rate limit raised to 200/min so the
  suite can create several users. The default limits are covered by unit tests.
* **GitHub Actions:** the pipeline definition was updated (full Ruff, frontend lint, migration step)
  and every step was reproduced locally, but the result of the next hosted run is not known until
  it executes. Hosted CI results could not be read from this environment.
* **Not tested:** the optional LLM/NLP features against real external providers; public HTTPS;
  load/performance beyond the earlier phase's results.

## 5. Evidence (run summary)

```
ruff:              All checks passed!
pip-audit:         No known vulnerabilities found
pip check:         No broken requirements found.
unit:              743 passed, 1 skipped, 1 warning in 120.93s
integration:       migrations applied: 14 -> 0014 (head); 36 passed in 31.24s
gitleaks v8.30.0:  no leaks found
tracked files:     No forbidden tracked files.
compose:           fails without APP_VERSION (expected); valid with it
frontend:          npm audit: found 0 vulnerabilities; build: passes
e2e (rc2 stack):   97 passed, 0 failed
```

Reproduce everything with the commands in [docs/LOCAL_DEVELOPMENT.md](../docs/LOCAL_DEVELOPMENT.md).
