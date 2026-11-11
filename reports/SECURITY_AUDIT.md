# Security Audit

**Scope:** application, database, container and CI configuration on `chore/final-completion`
(`main` at `76012ee` plus this phase's changes). **Method:** code review, automated tests, tool
scans, and live probes of a disposable Docker stack built from the release-candidate images
`0.6.0-rc2`. Production was not touched. No secret values appear in this report.

Legend: ✅ verified with evidence · ⚠️ partially addressed / accepted · ❌ open

## 1. Findings summary

| ID | Severity | Finding | Status |
|---|---|---|---|
| S-01 | High | Admin password exposed through database backups committed to the public repository earlier; the live admin password has **not been confirmed rotated** | ❌ Open — needs the owner (rotate first, then decide on history cleanup; `GIT_HISTORY_CLEANUP.md` is prepared, not run) |
| S-02 | High | Production runs release `0.5.0-p21`, which cannot read RBAC v2 roles or Argon2id hashes; RBAC v2 is built and tested but not deployed | ❌ Open — rollout plan in `DEPLOYMENT_REPORT.md`, awaiting approval |
| S-03 | Medium | The application connects to PostgreSQL with the database owner account (no separate runtime role with reduced rights) | ❌ Open — recommended hardening (separate migration and runtime roles) |
| S-04 | Medium | Public HTTPS is not deployed (TLS configuration exists but needs a domain and certificate) | ❌ Open — external prerequisite |
| S-05 | Low | Self-service password reset by email does not exist; recovery is by an operator CLI (`scripts/reset_password.py`) | ⚠️ Accepted limitation (needs SMTP and a product decision) |
| S-06 | Low | Frontend container's Nginx master process runs as root (standard `nginx:alpine`) with `read_only`, `cap_drop` and `no-new-privileges` | ⚠️ Accepted; switching to `nginx-unprivileged` is a possible follow-up |
| S-07 | Low | Access and refresh tokens are kept in `sessionStorage` (readable by script if XSS occurs); mitigated by a strict CSP and no `innerHTML` use | ⚠️ Accepted; httpOnly cookies would need CSRF protection |
| S-08 | Info | A UTF-16 build transcript (`docker-build.log`) had been tracked; it contained no secrets (only registry "pull token" labels) | ✅ Untracked and ignored |
| S-09 | Info | Gitleaks flagged an unsigned test token in a unit test (rule `jwt`, commit `9ccfa4d`) | ✅ Verified false positive; token now built at run time, one fingerprint ignored |

No new Critical issue was found. No authentication bypass, privilege escalation, injection or
path-traversal weakness was found in the areas tested below.

## 2. Control-by-control review

| Area | Evidence | Result |
|---|---|---|
| Authentication bypass | Unauthenticated requests to protected routes return 401 (E2E "requires auth" checks); forged/unsigned tokens get 401 (`test_rbac_matrix.py`); the role inside a token is ignored, the role is read from the database | ✅ |
| Broken access control | Every route × every role is tested (`test_rbac_matrix.py`); a route without a declared policy is refused (fail closed); object-level ownership isolation tested (E2E and `test_production_readiness.py`) | ✅ |
| Privilege escalation | Registration has no role field and rejects extra fields (422 for `role=admin/superadmin`); `PATCH /auth/me` accepts only `full_name` (422 for `role`, `is_active`, `permissions`); admin and user get 403 on role/superadmin endpoints; assignable roles are `user`/`admin` only; superadmin only via server-side CLI; last active superadmin cannot be removed (row-lock, PostgreSQL concurrency tests) | ✅ |
| Refresh-token replay | Rotation: a used refresh token is rejected (E2E); password change and logout revoke tokens (E2E) | ✅ |
| Password policy and storage | Minimum 8 characters with upper, lower and digit; Argon2id (19 MiB, t=2, p=1) with PBKDF2/bcrypt verification for legacy hashes; rehash-on-login is opt-in (`PASSWORD_REHASH_ON_LOGIN`, default off) | ✅ |
| SQL injection | All queries go through SQLAlchemy ORM/Core with bound parameters; the only raw SQL in `app/` is two constant statements (`SELECT 1`, `SHOW server_version`) | ✅ |
| XSS | React escaping; no `dangerouslySetInnerHTML`, `innerHTML` or `eval` in `frontend/src`; CSP `default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'self'` served by Nginx (verified live) | ✅ |
| CSRF | Authentication uses a Bearer header, not cookies; the API sets no cookies | ✅ (not applicable) |
| SSRF | The server makes outbound requests only to administrator-configured LLM endpoints (`OLLAMA_BASE_URL`, OpenAI); no endpoint fetches a user-supplied URL | ✅ |
| File upload | Extension allow-list (wrong type → 415), size and row/column limits, parsed as data never executed, stored under a generated name inside the upload directory | ✅ |
| Path traversal | `resolve_within()` for uploads and artifacts; artifact names must match a strict pattern; traversal attempts return 4xx (unit tests; live probe `..%2f..%2fetc/passwd` → 400/404) | ✅ |
| Model artifact tampering | SHA-256 stored in the database and verified before loading; tampered file rejected (unit test) | ✅ |
| CORS | No CORS headers are granted to a foreign origin (live preflight probe) | ✅ |
| Debug exposure | `APP_ENV=production` in Compose, `DEBUG=false`, API docs off by default (`/docs`, `/openapi.json` → 404 at the edge), error bodies use a fixed shape without stack traces | ✅ |
| Sensitive data in logs | Structured logs with request IDs; tokens/passwords are not logged; `LLM_LOG_CONTENT=false` by default; audit log stores no password material (E2E asserts this) | ✅ |
| Security headers | `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, CSP verified on the live edge; `server_tokens off`; HSTS is added only in the TLS configuration | ✅ (HSTS pending HTTPS) |
| Rate limiting | Per-bucket limits (default, auth, AI, training, analysis); 429 with `Retry-After` covered by unit tests | ✅ |
| Metrics endpoint | `/metrics` returns 404 at the public edge; the app endpoint requires `METRICS_TOKEN`; Prometheus is an opt-in internal overlay | ✅ |
| Audit-log immutability | PostgreSQL triggers reject UPDATE, DELETE and TRUNCATE (integration tests) | ✅ |
| Container hardening | `read_only`, `cap_drop: ALL`, `no-new-privileges`, tmpfs for writable paths; backend runs as user `app`; database not published; backend network is `internal` | ✅ (S-06 note) |
| Dependency pinning and vulnerabilities | `requirements.lock` via `-c` constraints; `pip-audit` clean; `npm audit` 0 vulnerabilities; `pip check` clean | ✅ |
| Secret management | `.env*` ignored (only `.example` files tracked); tracked-file guard; gitleaks over full history clean; Compose refuses to start without `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `APP_VERSION`; `scripts/preflight.py` checks secret strength | ✅ |
| Least-privilege database access | The app uses the database owner | ❌ S-03 |
| HTTPS | Not deployed; do not claim it | ❌ S-04 |

## 3. Residual risk and recommended next steps (in order)

1. **Rotate the admin password**, confirm it independently, then decide on the history cleanup
   (`GIT_HISTORY_CLEANUP.md`). Do not rewrite public history without a coordinated plan.
2. Deploy RBAC v2 using the plan in `DEPLOYMENT_REPORT.md` (backup, migrate, create superadmin,
   verify). Until then production keeps its current, older authorization model.
3. Add a reduced-privilege runtime database role (S-03).
4. Obtain a domain and certificate and deploy the TLS overlay; then verify HSTS and cookies/headers
   on the real hostname (S-04).
5. Consider httpOnly refresh cookies with CSRF protection, `nginx-unprivileged`, and a self-service
   password-reset flow if the product needs them.
