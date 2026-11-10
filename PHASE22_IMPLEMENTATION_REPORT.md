# Phase 22 Implementation Report

AIProject, 2026-11-11. Follows [PHASE22_PRODUCTION_HARDENING_REPORT.md](PHASE22_PRODUCTION_HARDENING_REPORT.md).

**Status: implemented and tested; release 0.5.1 images built (see section 0); NOT deployed.** The live stack still runs
the Phase 21 images (`0.5.0-p21`) on database revision 0013. No production file, credential,
container, volume or database was changed, and no Git history was rewritten.

## 0. Patch release 0.5.1 (current deployment candidate)

**Release `0.5.1` supersedes `0.5.0-p22` as the deployment candidate.** The `0.5.0-p22` frontend image
(`ca71d9937a67`) still shows the retired "first account becomes Administrator" text and **must not be
deployed**. The `0.5.0-p22` tags are kept for provenance only. Nothing is deployed; the live stack
still runs the Phase 21 images. Diagnosis: [REGISTRATION_API_DIAGNOSTIC.md](REGISTRATION_API_DIAGNOSTIC.md).

### What changed (frontend, scripts, tests, docs; no backend code)

| Change | File |
|---|---|
| Registration hint now reads: "New accounts have Viewer (read-only) access. An administrator can grant additional permissions." The form, fields and layout are unchanged | `frontend/src/components/AuthModal.tsx` |
| Dev proxy target comes from `VITE_DEV_API_TARGET` (read from the shell or `frontend/.env.local`), default `http://127.0.0.1:8000`; must be an `http(s)` origin or the dev server refuses to start. `/api`, `/docs` and `/openapi.json` all use it. Pointing it at the Docker stack: `$env:VITE_DEV_API_TARGET = "http://localhost"; npm run dev` | `frontend/vite.config.ts` |
| The development-only 502 message keeps its original text and now adds the proxy target it tried and how to switch to the Docker stack. The target is injected only for `npm run dev` (empty in production builds) and the whole branch is removed from production bundles | `frontend/src/services/api.ts`, `frontend/src/vite-env.d.ts` |
| `scripts/check_stack.py`: smoke test through the public origin (see tests) | `scripts/check_stack.py` |
| Docs: dev proxy, the new variable, the smoke script in the health-check table | `ENVIRONMENT_SETUP.md`, `DEPLOYMENT_GUIDE.md` |

The backend is **not changed and not rebuilt**: `aiproject-backend:0.5.1` is a second tag on the
verified `863bdd6fdd64`. Consequently `/health` reports `"version": "0.5.0"` (the unchanged package
version) and `"release": "0.5.1"` (the tag, from `APP_VERSION`).

### Regression tests added

| Test | Guards against |
|---|---|
| `tests/unit/test_frontend_consistency.py` (10) | the first-user-admin claim returning (regex over every frontend source file); the accurate hint text; the form still sending the same fields; the proxy target being re-hard-coded, ignoring the variable, or losing validation; dev target injected outside `serve`; the dev 502 branch losing its `DEV` guard; and, when `frontend/dist` exists, any dev diagnostic, proxy address or stale text in the production bundle |
| `tests/unit/test_check_stack.py` (9) | `scripts/check_stack.py` against simulated stacks: healthy; the web app answering every path (HTML 200 is a FAIL, never "healthy"); dead proxy (502 with the dev-server hint); missing route; a registration route that accepts an invalid body; rate limit (WARN); unreachable origin |
| `scripts/check_stack.py` (run against a live stack) | `GET /api/v1/health` is JSON 200 with `status: ok`; `GET /api/v1/auth/me` is 401 with the JSON error envelope; `GET /api/v1/auth/register` is 405; `POST /api/v1/auth/register` with a deliberately **invalid** body is 422 (the route accepts POST and nothing can be created; any 2xx is a FAIL); `GET /health` returning the web app's HTML is reported as WARN and never counted as API health |

The static tests were mutation-checked: restoring the stale sentence, re-hard-coding the proxy target
(three variants), removing the validation, and un-guarding the dev message each make a test fail.
Two of my first versions of the proxy test let a mutation through or failed on clean code; they were
corrected before use.

### Verification

| Check | Result |
|---|---|
| Frontend `tsc -b` and `npm run build` | pass |
| `oxlint` | no new findings (existing warnings only) |
| Production bundle (source build and inside the image) | absent: "API server is not running", "dev proxy could not reach", `VITE_DEV_API_TARGET`, `127.0.0.1:8000`, `python -m uvicorn`, "first account", "becomes the Administrator". Present: "grant additional permissions", "temporarily unavailable" |
| Dev server, proxy to the Docker stack (throwaway server on :3010) | `/api/v1/health` 200, `/api/v1/auth/me` 401, `/api/v1/auth/register` 405 through the dev proxy |
| Dev server, default target (:3011) | 502 as before (nothing on 8000) |
| Dev server, `VITE_DEV_API_TARGET=ftp://nope` (:3012) | refuses to start with a clear error |
| Dev client receives the configured target | confirmed in the served dev module |
| `scripts/check_stack.py` on the live stack (port 80) | 4 PASS, 1 WARN (`/health` is the web app's HTML); the user table was unchanged (2 users) afterwards |
| `scripts/check_stack.py` on the Vite dev server (:3000) | 4 FAIL with the explanatory 502 hint, reproducing the original symptom |
| Backend unit suite | **613 passed, 1 skipped** (594 before, plus 19 new) |
| Ruff `E9,F63,F7,F82`, `pip check` | clean |
| Backend sources since the image's build commit `252dd15` | 0 changes under `app/`, `alembic/`, `requirements*`, `Dockerfile`, `pyproject.toml`; the only change under `scripts/` is the new `check_stack.py` |
| Preflight and Compose dry run with `APP_VERSION=0.5.1` | passed; both images found; the plan recreates only `app`, `worker`, `frontend` |

The throwaway dev servers I started (:3010 to :3012) were stopped; your own dev server on :3000 was
left running and untouched.

### Release images and provenance

| Image | ID | Source |
|---|---|---|
| `aiproject-frontend:0.5.1` | `d1eb278fe206` | built from commit `18be2d945b9aff763e7076b0818196361a6a9b5e` using `git archive` (line-ending conversion off; the four changed files were byte-compared with the committed blobs) |
| `aiproject-backend:0.5.1` | `863bdd6fdd64` | **retag only** of `aiproject-backend:0.5.0-p22` (same ID, layers untouched). Built earlier from commit `252dd15`; re-verified: all 132 files under `app/`, `alembic/`, `scripts/` are byte-identical to the committed blobs at `18be2d9` (excluding `check_stack.py`, added after the build) |
| `aiproject-frontend:0.5.0-p22` | `ca71d9937a67` | kept, **do not deploy** (stale registration text) |
| `aiproject-backend:0.5.0-p22` | `863bdd6fdd64` | kept (same image as `0.5.1`) |
| p21 and `pre-p21` rollback images | unchanged | backend `83b37eaeee4a` / `67403b50fc14`, frontend `3fd9ea8bab02` / `97d04518bf28` |

### Deployment of 0.5.1 (supersedes the version numbers in section 6)

`.env` currently contains `APP_VERSION=0.5.0-p22` and `PASSWORD_REHASH_ON_LOGIN=false` (set by you;
this release did not touch `.env`). **Change `APP_VERSION` to `0.5.1`** before step 5 below; leave the
rehash switch `false` for the staged rollout. Where section 6 says `0.5.0-p22`, read `0.5.1`.
Everything else in section 6 is unchanged; add `python scripts\check_stack.py --origin http://localhost`
to the verification (step 7), and note that on release `0.5.1` `/api/v1/health` reports
`"release": "0.5.1"`.

Rollback to the previous release works as in section 7 (the pre-deploy backup, the `pre-p21`/p21
images, and the Argon2id precondition check are unchanged).

## 1. What changed

| Priority | Change | Main files |
|---|---|---|
| Hashing | Argon2id (19 MiB, 2 passes, 1 lane). PBKDF2 and bcrypt still verify. After a successful login an old hash is replaced (switchable, see 4) | `app/core/security.py`, `app/services/auth_service.py`, `requirements.txt`, `requirements.lock` |
| 2 Admin bootstrap | Public registration never creates an admin. First admin comes from `scripts/create_admin.py` (one-time, refuses if an active admin exists, never promotes or changes an existing account, password from env or hidden prompt, validated with the login endpoint's email rules). Legacy first-user rule only with `ALLOW_FIRST_USER_ADMIN=true`, refused when `APP_ENV=production` | `app/services/auth_service.py`, `app/api/routes/auth.py`, `app/core/config.py`, `scripts/create_admin.py` |
| 3 Version safety | Compose has no image-tag default (`${APP_VERSION:?...}`); `APP_RELEASE` reaches the containers and `/health` shows `release`; `scripts/preflight.py` rejects a missing value, `latest`, `0.4.0`, bad tags, weak secrets; `.env.production.example` pins `0.5.0-p21`; package version is `0.5.0` | `compose.yaml`, `scripts/preflight.py`, `.env.production.example`, `app/schemas/health.py`, `app/services/health_service.py`, `app/__init__.py`, `pyproject.toml` |
| 4 HTTPS (opt-in) | Server body shared by HTTP and TLS configs; `X-Forwarded-Proto` is believed only from a listed trusted proxy (none by default); HSTS only on HTTPS; TLS 1.2/1.3; `server_tokens off`; `compose.tls.yaml` needs your certificate folder | `frontend/nginx.conf`, `server-common.inc`, `proxy-trust.conf`, `nginx.tls.conf`, `security-headers.inc`, `frontend/Dockerfile`, `compose.tls.yaml`, `TLS_DEPLOYMENT.md` |
| 5 Metrics | Opt-in Prometheus (pinned v3.5.0), scrapes `app:8000/metrics` over the internal network with a bearer token read from a git-ignored file; published on 127.0.0.1 only. Public `/metrics` stays 404 | `compose.monitoring.yaml`, `monitoring/prometheus.yml`, `monitoring/secrets/.gitignore`, `MONITORING.md` |
| 6 CI | `secret-scan` job: full-history gitleaks (v8.30.0, `--redact=100`) plus `scripts/check_tracked_files.py`, which rejects tracked dumps, env files, keys and metrics tokens | `.github/workflows/ci.yml`, `.gitleaks.toml`, `scripts/check_tracked_files.py` |
| Docs | Deployment, environment and README text corrected; history-cleanup runbook prepared, not executed | `DEPLOYMENT_GUIDE.md`, `ENVIRONMENT_SETUP.md`, `README.md`, `GIT_HISTORY_CLEANUP.md` |

New settings (names only): `ALLOW_FIRST_USER_ADMIN` (default false), `PASSWORD_REHASH_ON_LOGIN`
(default true), `APP_RELEASE`; `APP_VERSION` is now required by Compose. New files for the
operator: `BOOTSTRAP_ADMIN_PASSWORD` (read only by `create_admin.py`), `TLS_CERT_DIR`,
`FRONTEND_TLS_PORT`, `PROMETHEUS_BIND`, `PROMETHEUS_PORT`, `monitoring/secrets/metrics_token`.

## 2. Bugs found and fixed while building it

| Found by | Problem | Fix |
|---|---|---|
| Running the candidate image | `create_admin.py` accepted `admin@example.test`, which the API's email validation rejects, so that admin could never sign in | The bootstrap validates with the same rules; regression test checks each rejected address against the real login endpoint |
| Reviewing rollback | Images before p22 cannot read Argon2id hashes, so an account upgraded by p22 would be locked out after a rollback | `PASSWORD_REHASH_ON_LOGIN` switch for a staged rollout (see 4) |
| Existing tests | `test_login_spends_password_work_for_unknown_emails` spied on a function login no longer calls; four production-settings tests collided with the new production guard | Spy re-pointed at `verify_and_rehash` with an added assertion that unknown accounts reach it with no stored hash; test helper applies the dev flag only to non-production settings. No assertion was weakened |
| Environment | The virtualenv had `bcrypt` 5.0.0, which passlib 1.7.4 cannot use, although `requirements.txt` pins `<5` | Aligned to `bcrypt==4.3.0` (already in the lock file and the images) |

## 3. Test results (all run on the finished code unless noted)

| Check | Result |
|---|---|
| Backend unit suite | **594 passed, 1 skipped** (optional `langchain_text_splitters`). Phase 21 baseline was 519 |
| New unit tests | `test_password_hashing.py`, `test_admin_bootstrap.py`, `test_deployment_hardening.py` (46 static and behaviour checks over compose, preflight, nginx, TLS, Prometheus, CI, tracked-file guard) |
| PostgreSQL 18 integration (throwaway container, tmpfs), re-run on the final committed code | 11 passed: 8-way concurrent bootstrap yields exactly one admin; six racing public registrations yield zero admins (and exactly one with the dev flag); legacy hash upgraded through a real login; job-claim and reaper race tests |
| Ruff `E9,F63,F7,F82` | clean |
| `pip check` | clean |
| `pip-audit -r requirements.lock` | no known vulnerabilities (includes `argon2-cffi` 25.1.0) |
| Frontend `tsc --noEmit`, `npm run build` | pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| Gitleaks over all 97 commits | 0 findings; a planted fake AWS key and GitHub token in a scratch repo were detected (exit 1, values redacted). **It does not detect the committed database dumps**, which is why `check_tracked_files.py` exists |
| Nginx (throwaway containers, read-only, dropped caps) | 22 of 22: HTTP stays plain; TLS mode redirects 301, serves HSTS, passes `https` upstream, refuses TLS below 1.2; spoofed `X-Forwarded-Proto` ignored from untrusted sources, honoured from a trusted subnet; `/metrics` 404 everywhere. Used a temporary self-signed certificate that was deleted |
| Prometheus (real image against a stub target) | `promtool` valid; right token: target up, metric ingested; wrong token: HTTP 401, target down |
| Candidate image, production mode, fresh PostgreSQL databases | migrates to 0013; bootstrap creates an Argon2id admin and refuses a second; no-password and `.test`-address cases refused; on an **empty** database the first public visitor is a `viewer`, `role=admin` is refused (403) and leaves no account; `/health` shows `release` and version `0.5.0`; `/openapi.json` 404 |
| Cross-version hash compatibility | A hash generated by the actual `pre-p21` image (PBKDF2-SHA256, 29,000 rounds, the format in your database) logs in on the p22 image, a wrong password changes nothing, and the first good login upgrades it to Argon2id once |
| Rehash switch, in the final image | With `PASSWORD_REHASH_ON_LOGIN=false` a hash made by the `pre-p21` image logs in and stays `pbkdf2-sha256` (zero upgrade log lines); with the default (on) it becomes `argon2id` after the first successful login (one log line); a wrong password changes nothing in either mode |
| Argon2id cost | verify about 48 ms (PBKDF2 was about 30 ms); a legacy login with upgrade about 77 ms |

**Not tested:** a certificate from a real CA, a real load balancer, browsers; scraping the real API
with `METRICS_TOKEN` set (token enforcement is covered by an existing unit test); the full Docker
stack on the p22 images (only the images were exercised); load or performance on p22 (see section
8); rollback from p22 to p21 on a live database.

## 4. Candidate images (built, not deployed)

| Image | ID | Note |
|---|---|---|
| `aiproject-backend:0.5.0-p22` | `863bdd6fdd64` | app, worker and migration; rebuilt from commit `252dd15` (see below) |
| `aiproject-frontend:0.5.0-p22` | `ca71d9937a67` | not rebuilt; its inputs were already committed and have not changed |
| `aiproject-backend:0.5.0-p21` (also `latest`) | `83b37eaeee4a` | running now |
| `aiproject-frontend:0.5.0-p21` (also `latest`) | `3fd9ea8bab02` | running now |
| `aiproject-backend:pre-p21` | `67403b50fc14` | rollback, kept |
| `aiproject-frontend:pre-p21` | `97d04518bf28` | rollback, kept |

**Provenance.** The backend image `863bdd6fdd64` was built from commit
`252dd15d003f60f8d3d0088626174038a6bb25ea` using `git archive` of that commit (line-ending
conversion disabled), with the same build arguments Compose uses (`INSTALL_LLM=false`,
`INSTALL_NLP=false`). The code changes are in commit `5996e5d` (`app/core/config.py`,
`app/services/auth_service.py`, password-hashing tests) and this report is in `252dd15`.
Every one of the 132 tracked files under `app/`, `alembic/` and `scripts/` in the image was
compared with the committed blob and is byte-identical.

Why it was rebuilt: the earlier build used this Windows working tree, so its files had CRLF line
endings while Git stores LF. The content was the same once line endings were ignored, but it was
not byte-identical to the commit. The image above is. The previous build (`8175cf6750eb`) was
removed. The `0.5.0-p22` tag was never deployed or shared; treat it as immutable from now on.

## 5. Migration status

No migration was added. Alembic head is `0013`, which the live database is already at. The p22
images need no schema change, so the `migration` service has nothing to do.

## 6. Deployment instructions (PowerShell; nothing below has been run)

Do these in order. Stop at any failed step.

1. **Rotate the admin password first, on the current p21 stack** (sign in, change password). It
   stays a PBKDF2 hash, so a rollback remains safe. This is the real fix for the public dumps
   (see [GIT_HISTORY_CLEANUP.md](GIT_HISTORY_CLEANUP.md)).
2. **Confirm the source is committed:** `app/core/config.py` and `app/services/auth_service.py` are in
   commit `5996e5d`. Before deploying, `git status` must be clean and `git log -1` must show a
   commit at or after `252dd15` (documentation-only commits after it do not change the image).
3. **Back up** (binary-safe; `>` redirection would corrupt the dump in PowerShell):
```powershell
New-Item -ItemType Directory -Force backups\phase22 | Out-Null
docker exec aiproject-db-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/pre_p22.dump'
docker cp aiproject-db-1:/tmp/pre_p22.dump backups\phase22\pre_p22.dump
docker exec aiproject-db-1 sh -c 'rm -f /tmp/pre_p22.dump'
Get-FileHash backups\phase22\pre_p22.dump -Algorithm SHA256 | Select-Object -ExpandProperty Hash | Out-File backups\phase22\pre_p22.dump.sha256
```
   The recipe was run against the live database for this report (read-only); the dump was valid.
4. **Edit `.env` yourself** (this report did not touch it): set `APP_VERSION=0.5.1` (it currently says
   `0.5.0-p22`; see section 0) and keep `PASSWORD_REHASH_ON_LOGIN=false` for the staged rollout.
5. **Preflight:** `python scripts\preflight.py --check-docker`. Warnings that running containers
   use `latest` are expected until step 6.
6. **Deploy only the stateless services** (about 20 to 30 seconds of interruption; the database
   container and every volume stay as they are):
```powershell
docker compose up -d --no-build --no-deps app worker frontend
docker compose ps
curl.exe -s http://localhost/api/v1/health      # "release":"0.5.1"
python scripts\check_stack.py --origin http://localhost   # expect PASSED (one WARN for /health is normal)
```
7. **Verify:** sign in as your admin; run a prediction; check `docker compose logs app worker --tail 50`
   for errors; confirm the worker is healthy. With the rehash switch off the admin's hash stays
   PBKDF2:
```powershell
docker exec aiproject-db-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select split_part(hashed_password, chr(36), 2), count(*) from users group by 1"'
```
8. **After a soak period** you are happy with, delete `PASSWORD_REHASH_ON_LOGIN=false` from `.env`
   and run `docker compose up -d --no-build --no-deps app`. Accounts upgrade as people sign in.
9. **Optional, separately:** HTTPS ([TLS_DEPLOYMENT.md](TLS_DEPLOYMENT.md)) and Prometheus
   ([MONITORING.md](MONITORING.md)). `ALLOW_FIRST_USER_ADMIN` must stay unset.

## 7. Rollback

- Config mistake with the new images: fix `.env` and rerun step 6.
- Back to the previous release: set `APP_VERSION=0.5.0-p21` in `.env`, then
  `docker compose up -d --no-build --no-deps app worker frontend`. **Precondition:** no account may
  hold an Argon2id hash, because p21 and older cannot read one. Check with
  `select count(*) from users where hashed_password like '$argon2%'`. It is zero while the
  rehash switch is off and nobody registered or changed a password on p22. If it is not zero, stay
  on p22 (with the switch off) or restore the pre-deploy dump into a **new** database and point
  `DATABASE_URL` at it. Never overwrite the live database; never run an Alembic downgrade.
- `pre-p21` images remain for the older rollback.

## 8. Remaining risks and open items

- **Public Git history still holds the database dumps.** Nothing in this phase changes that. Rotate
  the admin password, then decide on the rewrite in `GIT_HISTORY_CLEANUP.md` (prepared, not run).
- **Performance on p22 is unmeasured.** A repeatable load-test plan is in the Phase 22 audit report;
  no load test was run in this phase, as agreed. Argon2id adds about 18 ms per verification and
  about 19 MiB of memory per concurrent hash.
- `.env` still lacks `APP_VERSION`, so Compose commands (even `ps`) fail until you add it. That is
  the intended fail-safe.
- `METRICS_TOKEN` is unset on the live stack, so `/metrics` is open to containers on the internal
  network until you set it.
- TLS and Prometheus overrides are verified only on throwaway infrastructure.
- Email-parity validation applies to the bootstrap only; existing accounts are not re-validated.
- Cleanup left to you: leftover dangling image layers from the three rebuilds; the earlier
  Phase 21 test account and test data in the live database.

## 9. Safety rules kept

No `down -v`, no volume or database deletion, no downgrade, no production `.env` edit, no credential
change, no live admin password rotation, no Git history rewrite or force-push, no deployment, no
change to `ss_aiml_db` or the p20test stack. Every test database or container created for this phase
(`p22-*`, a throwaway PostgreSQL, throwaway Prometheus and nginx networks, temporary certificate and
token files) was removed afterwards.
