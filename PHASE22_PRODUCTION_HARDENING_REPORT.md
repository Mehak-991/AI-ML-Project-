# Phase 22 Production Hardening Report

AIProject v0.5.0-p21, audited 2026-11-11. **Audit only: no production file, image, credential, database or Git history was changed.** The only file written is this report. Evidence came from read-only commands; no secret values appear below.

## Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Public GitHub repo contains database dumps with the live admin's email and password hash | **Critical** | Needs your approval |
| 2 | Password hashing work factor is low (29,000 PBKDF2 rounds), no rehash on login | High | Fix proposed |
| 3 | First registered account on an empty database becomes admin | Medium | Fix proposed |
| 4 | Version safety: compose falls back to `0.4.0`, `.env` has no `APP_VERSION`, app still reports `0.4.0` | High | Fix proposed |
| 5 | No TLS, no HSTS, `X-Forwarded-Proto` is wrong behind a TLS terminator | High (internet) | Fix proposed |
| 6 | `METRICS_TOKEN` unset, no sanctioned way to scrape `/metrics` | Medium | Fix proposed |
| 7 | No repeatable load test in the repo; no Phase 20 load baseline exists | Low | Plan below |
| 8 | CI has dependency audits but no secret scanning | Low | Fix proposed |

## 1. Secrets and Git history (Priority 1)

**Evidence**
- Repository `Mehak-991/AI-ML-Project-` is **public** (unauthenticated GitHub API answers 200). 93 commits; `main` is pushed to `origin`.
- Two database dumps were committed and pushed: `backups/db_backup_aiproject_20261030_212154.sql.gz` (commit `e62825c`) and `backups/db_backup_aiproject_20261031_191321.sql.gz` (commit `93ce598`), plus their `.meta.json` and `.sha256` files. They are no longer tracked, but remain in history.
- Each dump contains 1 user row (email, PBKDF2-SHA256 password hash, role), 6–7 refresh-token rows (stored as hashes), and dataset, model and job metadata. They contain no database role passwords (no `ROLE`/`PASSWORD` statements).
- **The exposed password hash is identical to the live admin's current hash.** The admin's password has not changed since, so anyone can attack it offline (see finding 2 for the cost).
- `.env` was never committed. `.env.example` and `.env.production.example` have empty values for `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `METRICS_TOKEN` and `OPENAI_API_KEY`. Scans for AWS keys, GitHub tokens, Slack tokens and private keys found nothing. The one `sk-` pattern match is a fake test fixture (`tests/unit/ai/test_llm_openai.py`). Database URLs with passwords appear only in CI, tests and docs (disposable test values).
- Not exposed by this leak: the JWT signing key and the database password (neither is in history). Rotating them is not required by this finding.
- Refresh tokens: only hashes are stored, so the dumped rows cannot be replayed.

**Remediation (needs your approval for each step)**
1. **Rotate the admin password first** with the existing `POST /auth/change-password`. This changes the hash and, per the auth service, ends the account's other sessions. History cleanup does not help if the old password still works.
2. Consider the admin email exposed (PII). Decide whether to change it.
3. Rewrite history to remove `backups/`: `git filter-repo --path backups --invert-paths` on a fresh clone, then force-push `main`. Anyone with an existing clone or fork keeps the old data, and GitHub may cache objects; contact GitHub Support to purge cached views if needed. Rewriting history does not undo the exposure that has already happened, so step 1 is the real fix.
4. Make sure the whole `backups/` folder and `*.sql.gz` / `*.dump` are in `.gitignore`. Phase 21 dumps in `backups/phase21/` are already ignored; no backup file is tracked now.
5. Add secret scanning to CI (finding 8).

**Files:** `.gitignore`, `.github/workflows/ci.yml`. **Tests:** after cleanup, `git log --all -- backups` is empty; a fresh clone contains no `*.sql.gz`; old password returns 401.

## 2. Password hashing (found while auditing 1)

- `app/core/security.py:15` uses `CryptContext(schemes=["pbkdf2_sha256","bcrypt"])` with passlib defaults: **29,000 rounds** (live admin hash confirmed). Current OWASP guidance for PBKDF2-HMAC-SHA256 is 600,000.
- No `verify_and_update`, so existing hashes are never upgraded. Minimum password length is 8 (`app/schemas/auth.py`).
- **Fix:** set `pbkdf2_sha256__rounds=600000` (configurable via `PASSWORD_HASH_ROUNDS`), re-hash on successful login when `needs_update`, raise minimum length to 12 for new passwords only.
- **Tests:** hash and verify round-trip; legacy 29,000-round hash still verifies and is upgraded after login; login latency stays acceptable (measure; expect roughly 20x slower hashing, one hash per login).
- **Risk:** CPU cost per login rises; login rate limit already exists. Rollback: revert the setting; old hashes keep verifying.

## 3. Admin bootstrap and registration (Priority 2)

**Current behavior** (`app/services/auth_service.py:39-68`)
- Self-registration always yields `viewer`; requesting any other role without an admin caller returns 403 (verified live).
- If the users table is empty, the first registration becomes `admin` (serialized with a PostgreSQL advisory lock, so two simultaneous first requests cannot both win).
- **Risk:** a fresh deployment, or a restore into a new empty database (part of our own rollback plan if the dump is not restored), lets the first visitor become admin. The live system is not affected today: it already has an admin (2 users: the admin and the Phase 21 test viewer).

**Fix:** explicit bootstrap.
- Add `scripts/create_admin.py` (reads email and password from environment or a prompt, inserts the admin directly, refuses if an admin already exists unless `--force`).
- Add setting `ALLOW_FIRST_USER_ADMIN` (default `false` when `APP_ENV=production`). When false, the first registration is a `viewer` like any other.
- No change to existing accounts; no automatic promotion.
- **Files:** `app/services/auth_service.py`, `app/core/config.py`, new `scripts/create_admin.py`, `.env.production.example`, docs.
- **Tests:** empty DB + registration yields viewer in production; `create_admin.py` creates exactly one admin and refuses a second; admin self-role request still 403; concurrent registrations never create an admin; existing behavior unchanged in dev when the flag is true.
- **Rollback:** set `ALLOW_FIRST_USER_ADMIN=true` temporarily.

## 4. Deployment version safety (Priority 3)

**Evidence**
- `compose.yaml:51,81,136,186`: `${APP_VERSION:-0.4.0}`. `.env` has no `APP_VERSION`. `.env.production.example:23` says `0.4.0`. The Phase 21 stack runs only because `APP_VERSION=latest` was passed on the command line, so a plain `docker compose up` would look for a different image.
- `pyproject.toml:7` is `0.4.0`, so `/api/v1/health` reports `0.4.0` even though images are `0.5.0-p21`. Nothing running tells you which release it is.
- No preflight script checks tag, DB revision and image content together (`scripts/check_config.py` checks settings and, with `--db`, the migration revision).

**Fix**
- Change compose to `${APP_VERSION:?Set APP_VERSION, e.g. 0.5.0-p21}` (no fallback) for all four image lines. Keep `docker tag` aliases `0.5.0-p21` (exists).
- Set `pyproject.toml` version and the example to `0.5.0-p21` (PEP 440 requires care: use `0.5.0` in `pyproject.toml` and expose the full tag via a `RELEASE` build arg and env, returned by `/health`).
- New `scripts/preflight.ps1` (and `.sh`): fails if `APP_VERSION` is unset, `latest` or `0.4.0`; image `aiproject-backend:$APP_VERSION` and frontend exist; required secrets set (names only); compose config validates; DB revision equals image head; volumes `aiproject_pgdata`, `aiproject_models`, `aiproject_uploads` exist; current containers use the expected image IDs.
- Add `APP_VERSION=0.5.0-p21` to `.env` (an edit of a production file, needs approval).
- **Tests:** preflight fails with each bad input and passes on current state; `docker compose config` fails without `APP_VERSION`; `/health` shows the release.
- **Rollback:** revert compose; pass `APP_VERSION=pre-p21` for the old images.

## 5. HTTPS and security headers (Priority 4)

**Evidence** (`frontend/nginx.conf`, `frontend/security-headers.inc`)
- Good already: CSP without `unsafe-inline` scripts, `X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `/docs` and `/metrics` blocked, read-only containers.
- Missing: any TLS listener, HTTP to HTTPS redirect, HSTS, `server_tokens off` (to verify), and `proxy_set_header X-Forwarded-Proto $scheme` reports `http` when a TLS terminator sits in front, so the API cannot tell requests were secure.
- Tokens live in `sessionStorage` (`frontend/src/services/api.ts`), not cookies, so cookie flags (`Secure`, `HttpOnly`, `SameSite`) do not apply. A strict CSP limits XSS exposure but does not remove it. Moving refresh tokens to `HttpOnly` cookies would be a larger change with CSRF consequences; deferred, not recommended now.
- CORS in production defaults to none (same origin), rejects `*`. Good.

**Fix** (no certificates are created; you supply them)
- Add `frontend/nginx.tls.conf` as an opt-in template: port 80 redirects to 443, TLS 1.2+/1.3, modern ciphers, `Strict-Transport-Security: max-age=31536000; includeSubDomains` (start with a short max-age), OCSP stapling off by default, certificates mounted read-only from `${TLS_CERT_DIR}`.
- Add `compose.tls.yaml` override (publishes 443, mounts certs). Default `compose.yaml` and `compose.dev.yaml` stay HTTP so local development is unchanged.
- Use a `map $http_x_forwarded_proto $fwd_proto { default $scheme; https https; }` only when `TRUSTED_TLS_TERMINATOR` is set; otherwise nginx's own `$scheme`.
- Add `server_tokens off;`.
- **Env:** `TLS_CERT_DIR`, `TLS_SERVER_NAME`, `FRONTEND_TLS_PORT`.
- **Tests:** `nginx -t` on both configs; redirect returns 301; HSTS only on HTTPS; headers present on every location (including error pages); HTTP default stack still returns 200; `ssllabs`-style check with `openssl s_client` once real certificates exist (cannot be verified now: no certificate).
- **Rollback:** do not include `compose.tls.yaml`.

## 6. Metrics and observability (Priority 5)

**Why `/metrics` is inaccessible:** deliberate. `frontend/nginx.conf` has `location = /metrics { return 404; }`, so it is not public. From inside the stack it works: `http://app:8000/metrics` returns 200 with 28 lines including `aiml_worker_health_status 1`. `/api/v1/jobs/metrics` needs authentication.

**Gap:** `METRICS_TOKEN` is not set in the live app, so any container that can reach `app:8000` can read metrics. Only nginx and the worker share its networks today, so exposure is low, but no scraper is provided.

**Fix**
- Generate a token and store it as a Docker secret/file (not committed); set `METRICS_TOKEN` (name only here).
- Add an opt-in `compose.monitoring.yaml`: Prometheus on the internal `backend` network (no published port, or bound to `127.0.0.1` only), `scrape_configs` with `authorization: credentials_file`, target `app:8000`, `metrics_path: /metrics`, 30 s interval. Optional: Grafana bound to localhost.
- Leave nginx's 404 in place. Worker heartbeat file and `check_worker_health.py` are unchanged.
- **Tests:** scraping without token returns 401; with token returns 200 and expected metric names; `curl http://localhost/metrics` stays 404; worker health still passes; Prometheus target reports up.
- **Rollback:** unset `METRICS_TOKEN`, stop the monitoring override.

## 7. Performance (Priority 6)

**Current configuration (live):** 2 uvicorn workers; DB pool 5 + 10 overflow per process (max 45 across app workers and worker; PostgreSQL `max_connections` 100, 5 connections in use at idle); job worker has 3 threads, polls every 2 s, stale timeout 15 min, reaper every 60 s; app and worker memory limit 2 GB.

**Baseline:** there is **no Phase 20 load baseline** in the repo or reports (Phase 20 recorded single-client latency only), so no comparison with it is possible. The only load numbers are the Phase 21 runs on the p20test stack (old image, relaxed rate limits): throughput peaked near 131 req/s at 10 users; at 100 users p95 was 3.3 s with 0 errors; the app was CPU-bound (~175%) with the database at ~29% CPU. Those numbers describe the old image and are not a baseline for `0.5.0-p21`.

**Plan (not executed; no load against production)**
1. Commit the load script to `tests/load/loadtest.py` (asyncio/httpx, same bounds: 1/10/50/100 users, 20 s, ramp-up, abort at 20% errors or p95 > 10 s), parameterized by base URL and credentials from environment variables.
2. Start a **separate** stack from the `0.5.0-p21` images on a new compose project name (new volumes, new port), the same method as p20test. Do not reuse p20test (it holds old images).
3. Collect `docker stats` during each level (the Phase 21 run sampled too late), PostgreSQL `pg_stat_activity` counts, job queue latency (submit to `started_at`), and prediction latency.
4. Tuning candidates to test one at a time: `--workers 4` for the API; pool sizes; `JOB` worker thread count (currently a constant, needs a setting). Compare each against the same script.
- **Tests required:** repeatable run produces the same table format as `PRODUCTION_READINESS_REPORT.md`; results stored under `tests/load/results/` with date and image tag.

## 8. CI

- `.github/workflows/ci.yml` runs `pip-audit` and `npm audit --audit-level=high` but no secret scanner. Add `gitleaks` (or `trufflehog`) on pull requests and a Trivy image scan. Requires deciding on third-party actions.

## Implementation order and approvals

| Step | Needs approval for | Risk |
|---|---|---|
| A. Rotate admin password (finding 1) | A production credential change (done by you, or by me with your password) | Low |
| B. Add `APP_VERSION` to `.env` and require it in compose; preflight script | Editing production `.env` and compose | Low |
| C. Password rounds and rehash on login; `ALLOW_FIRST_USER_ADMIN`, `create_admin.py` | Rebuild and redeploy images (new tag, e.g. `0.5.1-p22`) | Medium |
| D. TLS templates, monitoring override | New opt-in files only; enabling needs certificates and your decision | Low |
| E. Git history rewrite and force-push | Explicit approval; affects every clone | High |
| F. Load-test script and run on a separate stack | New stack only | Low |

## Required environment variables (names only)

`APP_VERSION`, `ALLOW_FIRST_USER_ADMIN`, `PASSWORD_HASH_ROUNDS`, `METRICS_TOKEN`, `TLS_CERT_DIR`, `TLS_SERVER_NAME`, `FRONTEND_TLS_PORT`, `TRUSTED_TLS_TERMINATOR`, plus existing `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `DATABASE_URL`, `FORWARDED_ALLOW_IPS`.

## Rollback strategy

- Images: `pre-p21` tags still exist; each new release gets its own tag and the previous one stays available.
- Database: no schema change is proposed in this phase. If one is added later, take a verified dump first; never downgrade, restore into a new database instead.
- Config: every change above is behind a setting or an opt-in override file and can be reverted without data loss.
- Git: take a mirror clone (`git clone --mirror`) before any history rewrite and keep it offline.

## Not verified in this audit

- Whether anyone has forked or cloned the public repo, or cached the dumps.
- TLS behavior (no certificate available).
- Whether the client-supplied `X-Forwarded-For` can influence rate limiting through nginx's `$proxy_add_x_forwarded_for` (uvicorn trusts only the nginx address; behavior not tested).
- Performance of the `0.5.0-p21` images under load.
