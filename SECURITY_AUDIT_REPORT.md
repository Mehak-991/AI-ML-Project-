# Security Audit Report

AIProject v0.4.0, 2026-11-03. Each row states the outcome and how it was checked. No secret values
appear in this report.

## Action required

| Severity | Item | What to do |
|---|---|---|
| **High** | Two database dumps are in the git history on `origin` (commits `e62825c`, `93ce598`). They hold one user row each (email, PBKDF2 hash) and refresh-token hashes. They were removed from the current tree, not from history | Treat them as exposed. Change that account's password, which also revokes its refresh tokens. If the repository is or was public, rewrite history with `git filter-repo --path backups --invert-paths` and force-push; this needs your decision because it rewrites shared history. Repository visibility could not be checked from here |
| **Medium** | The first account to register becomes admin | Register your admin before the service is reachable by anyone else |
| **Medium** | Nginx serves plain HTTP | Put a TLS terminator in front. Passwords and tokens must not cross a network unencrypted |

## Findings by area

| Area | Before | Now | Verified by |
|---|---|---|---|
| JWT signing secret | Default accepted in production (critical log only) | Startup refused if default or under 32 bytes | Unit test; container exits with a clear error |
| JWT validation | Signature and expiry if present | `exp` and `sub` required, access type enforced, HMAC-only algorithm allowlist | Unit tests |
| Refresh tokens | Rotated, but racy; replay ignored | Stored as SHA-256; atomic rotation; replay revokes all sessions | Unit tests; end-to-end |
| Password hashing | PBKDF2-SHA256 with bcrypt legacy support | Unchanged; strength rules unchanged | Reviewed |
| Login enumeration | Timing difference on unknown email | Equal hashing work. Register still answers 409 for a taken email (accepted for usability) | Unit test |
| Missing authentication | 7 routes open | All require login; only `/`, health and login/register/refresh/logout are public | Unit tests; end-to-end |
| RBAC | Correct where applied | Unchanged, extended to `datasets/validate` | Unit tests |
| Object-level authorization | Missing on datasets, experiments, deployments, drift, monitoring, one explainability route | Enforced; listings scoped | 19-route denial test; end-to-end |
| Rate limiting | Per IP, per process; expensive routes under-limited; compose could collapse all clients into one IP | Expensive routes limited; proxy trust fixed. Still per process (documented) | Unit test; observed 429s under load; API sees non-proxy client IP |
| CORS | Restrictive; `*` refused in production | Unchanged | Existing tests |
| SQL injection | ORM with bound parameters throughout | One exception fixed: database name in the restore script. `LIKE` search uses bound parameters but doesn't escape `%` and `_` (admin-only, harmless) | Code review; unit test |
| XSS | React escaping; no `dangerouslySetInnerHTML` found | CSP added: scripts only from same origin | Code search; headless browser shows no CSP violations |
| CSRF | Not applicable: bearer tokens in a header, no cookies | Unchanged | Reviewed |
| Token storage | `sessionStorage`, readable by page scripts | Unchanged, documented risk | Reviewed |
| File uploads | Extension allowlist, content sniffing, zip-bomb ratio, generated names, streaming size limit | Unchanged, now behind login. No malware scanning | Existing tests; end-to-end |
| Path traversal | `resolve_within` with strict name pattern; clients never supply paths | Unchanged | Reviewed; existing tests |
| Unsafe deserialization | joblib only from `MODEL_DIR`, hash-checked first | Hash check kept; runs once per file version. Write access to `MODEL_DIR` plus the database still means code execution (documented) | Code review |
| Secrets | `SecretStr`; `.env` ignored by git | Production needs explicit secrets; `DATABASE_ECHO` refused in production | Passwords, JWT secret and tokens: 0 matches in all container logs |
| Error messages | Sanitized envelope | Unchanged. Experiment and job error text can include library messages, visible only to the owner | Reviewed |
| `/metrics` | Public on the API port; not routed by Nginx | Optional `METRICS_TOKEN`; Nginx returns 404 | Unit test; `curl` through Nginx |
| Docs | On by default in compose | Off unless `PROD_DOCS_ENABLED=true` | End-to-end check |

## Containers

Verified with `docker inspect` on the running stack:

| Service | User | Read-only root | Capabilities | Published port |
|---|---|---|---|---|
| `app` | 10001 | yes | none | none |
| `worker` | 10001 | yes | none | none |
| `frontend` | master root, workers `nginx` | yes | CHOWN, SETGID, SETUID, NET_BIND_SERVICE | `FRONTEND_PORT` |
| `db` | root at entry, drops to `postgres` | no | minimal set | none, internal network |

All use `no-new-privileges`. `frontend` previously kept all default capabilities and a writable root.

## Dependencies

| Check | Result |
|---|---|
| `pip-audit` on the 69 exact versions in the production image | No known vulnerabilities |
| `npm audit --audit-level=high` | 0 vulnerabilities |

`pip-audit` previously ran on unpinned ranges in CI; it now audits `requirements.lock`.
These results are as of 2026-11-03 and change as advisories are published.

Note: the local `.venv312` has `bcrypt` 5.0.0, outside the `bcrypt<5` range in `requirements.txt`,
while the image has 4.3.0. Current passwords use PBKDF2, so nothing is affected today. Reinstall
from `requirements.lock` to align them.

## Accepted limitations

These are documented rather than fixed because a fix needs infrastructure or a product decision:

- Rate limits and the model cache are per process, so with 2 workers the effective limit is up to 2×.
  You asked not to add Redis without a real need, and a gateway limiter is the usual answer.
- `GET /monitoring/overview` returns platform-wide counts to any signed-in user. It holds counts
  only, no object details.
- Access tokens stay valid until expiry (30 minutes) after a password change. Deactivation and role
  changes take effect immediately because the user is re-read on every request.
- Datasets and experiments with no owner stay visible to all signed-in users. That covers your 4
  existing datasets until you assign owners; no API exists for that yet.
- Expired refresh tokens are never purged, so that table grows slowly.
