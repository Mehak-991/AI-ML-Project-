# RBAC V2 Implementation Report

**Branch:** `feature/rbac-v2` (HEAD `f89c040`, images built from `531b99e`) · **Release candidate:** `0.6.0-rc1`
**Status:** implemented and verified in isolated environments only. **Nothing has been applied to production.**

> Production still runs the p21 images (backend `83b37eaeee4a`, frontend `3fd9ea8bab02`) on database
> revision `0013`, with roles `admin=1`, `viewer=2`. Migration 0014 has not been run on it, no
> account has been promoted, `scripts/create_superadmin.py` has not been run against it, `.env` is
> unchanged, no container was restarted or deployed, and no user, resource or Docker volume was
> touched. The p21 and p22 rollback images are preserved. Git history was not rewritten.

---

## 1. Summary

| Requirement | Result |
|---|---|
| Exactly three roles `user` / `admin` / `superadmin` | Done. Single definition in `app/core/permissions.py`; any other stored role has no permissions |
| Centralized permission registry | Done. 11 permissions, `ROLE_PERMISSIONS` map; routes declare a permission, never a role |
| Deny-by-default routes | Done. App-level `enforce_route_policy` refuses (403) any route that declares neither a permission nor `PublicRoute`. Proven by mutation test |
| Backend is the source of truth | Done. `/auth/me` returns the server-computed `permissions`; the UI only hides what the API would refuse |
| Atomic role changes + last-superadmin protection | Done. Row locks (`SELECT … FOR UPDATE`) verified on real PostgreSQL under concurrency |
| `audit_logs` | Done. Same-transaction writes; PostgreSQL triggers reject UPDATE/DELETE/TRUNCATE |
| No role in public registration | Done. Payload has no role field (`extra=forbid`); every registration creates a `user` |
| Admin capabilities preserved | Done. Admin keeps ML management and deployment management (D2) |
| Migration 0014 (viewer→user, admin→admin, abort on unmapped `ml_engineer`) | Done. Tested on SQLite and PostgreSQL, upgrade and downgrade, plus a rehearsal on a restored copy of the real backup |
| Bootstrap and recovery CLIs | Implemented, tested, **not executed on production** |
| Tests | 724 unit passed + 36 PostgreSQL integration passed (see §9) |
| Frontend role-based navigation/UI | Done. Permission-driven nav, gated actions, new Audit and Settings pages |

## 2. Old vs new authorization

| | Before (v1) | After (v2) |
|---|---|---|
| Roles | `admin`, `ml_engineer`, `viewer` (stored strings, checked by `require_role(...)` per route) | `user`, `admin`, `superadmin` |
| Route protection | Per-route role lists; an unannotated route was open to any login | Per-route **permission**; an unannotated route is refused |
| First account | "First registration becomes admin" (`ALLOW_FIRST_USER_ADMIN`) | Removed. Superadmin comes only from the server-side CLI |
| User management | `admin` | `superadmin` only (D4) |
| Auditing | None | Append-only `audit_logs` |
| Registration | Could carry a role in some paths | No role field exists |
| Last admin | Not protected | Last active superadmin cannot be demoted, deactivated or deleted |

## 3. Roles and permissions (D1–D4)

| Permission | user | admin | superadmin |
|---|:-:|:-:|:-:|
| `resources:read` | ✔ | ✔ | ✔ |
| `predict:run` (predictions, SHAP/LIME, embeddings, NLP classify, token count) | ✔ | ✔ | ✔ |
| `profile:manage` | ✔ | ✔ | ✔ |
| `ml:operate` (upload, train, experiments, jobs, drift, ground truth, LLM) |  | ✔ | ✔ |
| `deployments:manage` |  | ✔ | ✔ |
| `users:read`, `users:manage` |  |  | ✔ |
| `roles:assign`, `superadmin:grant` |  |  | ✔ |
| `audit:read`, `settings:read` |  |  | ✔ |

Object-level rules still apply on top: `admin` and `superadmin` see every resource; a `user` sees
what they own plus resources with no owner (`has_full_resource_access`). D1: no new candidate entity
was introduced; roles apply to the existing resources. D7: deactivation is the default and a hard
delete is refused if the account owns resources or `confirm_email` does not match.

## 4. Endpoint → permission mapping

Generated from the running application (`70` method/path pairs, `67` under the API; every pair
declares a policy, enforced by `tests/unit/test_rbac_matrix.py`).

| Method | Path | Required permission | Lowest role |
|---|---|---|---|
| GET | `/` | public | anyone |
| GET | `/api/v1/ai/status` | `resources:read` | user |
| GET | `/api/v1/audit-logs` | `audit:read` | superadmin |
| POST | `/api/v1/auth/change-password` | `profile:manage` | user |
| POST | `/api/v1/auth/login` | public | anyone |
| POST | `/api/v1/auth/logout` | public | anyone |
| GET | `/api/v1/auth/me` | `profile:manage` | user |
| PATCH | `/api/v1/auth/me` | `profile:manage` | user |
| POST | `/api/v1/auth/refresh` | public | anyone |
| POST | `/api/v1/auth/register` | public | anyone |
| GET | `/api/v1/auth/users` | `users:read` | superadmin |
| POST | `/api/v1/auth/users` | `users:manage` | superadmin |
| DELETE | `/api/v1/auth/users/{user_id}` | `users:manage` | superadmin |
| PATCH | `/api/v1/auth/users/{user_id}` | `users:manage` | superadmin |
| DELETE | `/api/v1/auth/users/{user_id}/superadmin` | `superadmin:grant` | superadmin |
| POST | `/api/v1/auth/users/{user_id}/superadmin` | `superadmin:grant` | superadmin |
| GET | `/api/v1/datasets` | `resources:read` | user |
| POST | `/api/v1/datasets` | `ml:operate` | admin |
| POST | `/api/v1/datasets/validate` | `ml:operate` | admin |
| GET | `/api/v1/datasets/{dataset_id}` | `resources:read` | user |
| GET | `/api/v1/datasets/{dataset_id}/summary` | `resources:read` | user |
| GET | `/api/v1/deployments` | `resources:read` | user |
| GET | `/api/v1/deployments/{deployment_id}` | `resources:read` | user |
| GET | `/api/v1/drift/alerts` | `resources:read` | user |
| POST | `/api/v1/drift/alerts/{alert_id}/resolve` | `ml:operate` | admin |
| GET | `/api/v1/drift/models/{model_id}/alerts` | `resources:read` | user |
| POST | `/api/v1/drift/models/{model_id}/analyze-drift` | `ml:operate` | admin |
| POST | `/api/v1/drift/models/{model_id}/analyze-performance` | `ml:operate` | admin |
| POST | `/api/v1/drift/models/{model_id}/analyze-quality` | `ml:operate` | admin |
| GET | `/api/v1/drift/models/{model_id}/reports` | `resources:read` | user |
| GET | `/api/v1/drift/overview` | `resources:read` | user |
| POST | `/api/v1/embeddings` | `predict:run` | user |
| GET | `/api/v1/experiments` | `resources:read` | user |
| POST | `/api/v1/experiments` | `ml:operate` | admin |
| GET | `/api/v1/experiments/compare` | `resources:read` | user |
| GET | `/api/v1/experiments/{experiment_id}` | `resources:read` | user |
| POST | `/api/v1/experiments/{experiment_id}/cancel` | `ml:operate` | admin |
| POST | `/api/v1/experiments/{experiment_id}/rerun` | `ml:operate` | admin |
| POST | `/api/v1/experiments/{experiment_id}/run` | `ml:operate` | admin |
| GET | `/api/v1/health` | public | anyone |
| GET | `/api/v1/jobs` | `resources:read` | user |
| POST | `/api/v1/jobs` | `ml:operate` | admin |
| GET | `/api/v1/jobs/metrics` | `resources:read` | user |
| GET | `/api/v1/jobs/{job_id}` | `resources:read` | user |
| POST | `/api/v1/jobs/{job_id}/cancel` | `ml:operate` | admin |
| GET | `/api/v1/jobs/{job_id}/result` | `resources:read` | user |
| POST | `/api/v1/jobs/{job_id}/retry` | `ml:operate` | admin |
| POST | `/api/v1/llm/chat` | `ml:operate` | admin |
| GET | `/api/v1/models` | `resources:read` | user |
| POST | `/api/v1/models/train` | `ml:operate` | admin |
| GET | `/api/v1/models/{model_id}` | `resources:read` | user |
| POST | `/api/v1/models/{model_id}/deploy` | `deployments:manage` | admin |
| GET | `/api/v1/models/{model_id}/explainability/feature-importance` | `resources:read` | user |
| POST | `/api/v1/models/{model_id}/explainability/lime` | `predict:run` | user |
| POST | `/api/v1/models/{model_id}/explainability/shap` | `predict:run` | user |
| GET | `/api/v1/models/{model_id}/explainability/summary` | `resources:read` | user |
| POST | `/api/v1/models/{model_id}/predict` | `predict:run` | user |
| GET | `/api/v1/models/{model_id}/predictions/history` | `resources:read` | user |
| POST | `/api/v1/models/{model_id}/undeploy` | `deployments:manage` | admin |
| GET | `/api/v1/monitoring/models/{model_id}` | `resources:read` | user |
| GET | `/api/v1/monitoring/overview` | `resources:read` | user |
| POST | `/api/v1/nlp/analyze` | `ml:operate` | admin |
| POST | `/api/v1/nlp/classify` | `predict:run` | user |
| GET | `/api/v1/predictions/history` | `resources:read` | user |
| GET | `/api/v1/predictions/history/{prediction_id}` | `resources:read` | user |
| POST | `/api/v1/predictions/history/{prediction_id}/ground-truth` | `ml:operate` | admin |
| GET | `/api/v1/system/settings` | `settings:read` | superadmin |
| POST | `/api/v1/tokens/count` | `predict:run` | user |
| GET | `/health` | public | anyone |
| GET | `/metrics` | public | anyone |


## 5. Account administration rules

- `PATCH /auth/users/{id}` may only set `user` or `admin` (`AssignableRole`); it cannot grant `superadmin`.
- `POST|DELETE /auth/users/{id}/superadmin` grant and revoke superadmin; both audited.
- `_guard_last_superadmin` takes `lock_active_superadmins` (`FOR UPDATE`) and refreshes the target, so two concurrent demotions of the last two superadmins cannot both succeed. Removing the lock makes the concurrency tests fail (mutation verified).
- Deactivation revokes sessions; deletion needs `confirm_email` and refuses accounts that own resources.
- Self-service (`PATCH /auth/me`) can change name and password only, never role.

## 6. Audit log

Table `audit_logs`: id, timestamp, `action`, actor id/email/role snapshot, target id/email snapshot, JSON
`before`/`after`, `detail`, `request_id`, `client_ip`. No foreign keys, so entries survive user deletion. PostgreSQL
triggers `audit_logs_no_change` and `audit_logs_no_truncate` reject UPDATE, DELETE and TRUNCATE
(verified at the database level). Recorded actions: `user.registered/created/role_changed/deactivated/reactivated/profile_updated/deleted`,
`superadmin.granted/revoked`, `deployment.deployed/undeployed`, `cli.superadmin_bootstrap`,
`cli.password_reset`, `migration.role_mapped`. Read via `GET /api/v1/audit-logs` (superadmin) and the Audit page.

## 7. Migration 0014 and compatibility

`alembic/versions/20261111_0014_rbac_v2_roles_and_audit.py`

| Stored role (0013) | After 0014 |
|---|---|
| `viewer` | `user` (audited) |
| `admin` | `admin` (unchanged; **not** promoted) |
| `ml_engineer` | **Abort** unless `-x ml_engineer=user\|admin` is given; the choice is audited |
| anything else | Abort |

It also creates `audit_logs`, the immutability triggers, server default `'user'`, and the CHECK
`ck_users_role` (allows `user/admin/superadmin` plus `viewer` until the contract release).
Downgrade maps `user→viewer`, `superadmin→admin`, and **refuses** to drop audit entries unless
`-x audit_export=<new file>` is supplied. No superadmin is created by the migration.

**Expand → migrate → contract (D5).** v2 code reads legacy `viewer`/`ml_engineer` as `user` and
unknown roles as no permissions, so v2 code runs against a 0013 database and v1 code runs against
a 0014 database while `RBAC_STORE_LEGACY_VIEWER=true`. The `viewer` CHECK allowance is removed in a later release.

**Rehearsal on a restored copy of the real production backup** (throwaway PostgreSQL, backup *file*
only; production untouched):
- restore OK at 0013; upgrade to 0014 succeeded; every table identical except the intended `users.role` change; roles `admin,viewer,viewer → admin,user,user`; 0 superadmins created; triggers present
- downgrade to 0013 restored the original data **exactly** (row counts and content hashes equal)
- an added `ml_engineer` account made the upgrade abort with no change to the database and no `audit_logs` table; with `-x ml_engineer=user` it migrated and wrote an audit entry

## 8. Bootstrap and recovery CLIs (not executed on production)

| Script | Purpose | Safety |
|---|---|---|
| `scripts/create_superadmin.py --email X` | Create the first superadmin | Refuses if migration 0014 is absent, if a superadmin exists, or if the email exists; password from `BOOTSTRAP_SUPERADMIN_PASSWORD` or hidden prompt, never argv; audited |
| `… --email X --promote` | Promote one **explicitly named** existing account | Requires typing the exact email (or `--yes`); never chooses an account itself (D6) |
| `scripts/reset_password.py --email X` | Recovery: reset a password | Password from `RESET_PASSWORD` or hidden prompt; revokes sessions; audited |
| `scripts/create_admin.py` | Legacy, pre-v2 | Marked legacy |

Executed only in unit tests and on the disposable stack (§9).

## 9. Test evidence

| Suite | Result |
|---|---|
| Backend unit (final run) | **724 passed, 1 skipped** |
| Backend integration with real PostgreSQL | **36 passed** |
| Lint (`ruff`), `pip check`, `pip-audit` | clean / no conflicts / no known vulnerabilities |
| Frontend `tsc`, production build, `npm audit` | pass / pass / 0 vulnerabilities (oxlint: pre-existing style warnings only) |
| Disposable full stack (`aiproject-rbac2`, no Docker volumes) | migrated to 0014 on an empty DB; `scripts/e2e_check.py` **68/68**; `check_stack.py` pass |

Coverage highlights:
- **Matrix** (`test_rbac_matrix.py`): every route × every role, forged/unsigned tokens, and a token whose role claim is not trusted.
- **Mutation checks, all caught by the tests:** granting `ml:operate` to `user`; loosening the jobs alias; removing deny-by-default; removing `FOR UPDATE`; removing frontend gates.
- **Concurrency on PostgreSQL:** 25 fresh pairs demoting each other, a ring of five, a bootstrap race, concurrent registrations. Exactly one survivor each time; zero admins from registration.
- **Registration:** role/permission fields rejected; the first user is a plain `user`.
- **Migration:** SQLite and PostgreSQL, upgrade, downgrade, unmapped-role abort, explicit mapping.
- **Audit:** same-transaction writes, rollback leaves no entry, DB-level UPDATE/DELETE/TRUNCATE refused.
- **Frontend:** permission-filtered navigation, gated buttons, audit and settings pages (`test_frontend_rbac.py`).
- **Password hashing:** Argon2id with rehash on login; PBKDF2/bcrypt legacy verification.

## 10. Frontend

Navigation and actions are driven by `user.permissions` from `/auth/me` (`can(permission)`).
`user` sees read-only views and prediction/explainability; `admin` additionally sees upload, train,
jobs, experiments, drift and deployment controls; `superadmin` additionally sees User Management,
Audit Logs and System Settings. Registration text reads "New accounts have User (read-only) access.
A superadmin can grant additional permissions." The UI is a convenience; the API enforces every rule.

## 11. Candidate images

| Image | ID | Built from |
|---|---|---|
| backend `0.6.0-rc1` | `d8e5d5baf6cb` | `531b99e` via `git archive` (byte-exact) |
| frontend `0.6.0-rc1` | `19b123ad0a4a` | `531b99e` |

No image input (app, alembic, scripts, frontend, requirements, Dockerfile, pyproject) changed after
`531b99e`; only tests and docs followed. Not deployed. Rollback images (p21, p22 / 0.5.1) are untouched.

## 12. Deployment instructions (do not run until separately approved)

1. **Backup** the production database with the existing backup procedure and verify it restores into a disposable database.
2. **Expand:** deploy the v2 images with `RBAC_STORE_LEGACY_VIEWER=true`; v2 runs on revision 0013. Confirm health and a normal login.
3. **Review** accounts: the existing `admin` stays `admin`, two `viewer` accounts become `user`. Decide on any `ml_engineer` before migrating (none exist today).
4. **Migrate:** `alembic upgrade 0014`. It aborts on anything unmapped and changes nothing in that case.
5. **Bootstrap:** run `create_superadmin.py` for **the account you name** (new account, or `--promote` of an existing one).
6. **Verify:** `scripts/e2e_check.py` with `E2E_SUPERADMIN_EMAIL/PASSWORD`, `check_stack.py`, review the audit log.
7. **Contract** (later release): set `RBAC_STORE_LEGACY_VIEWER=false`, drop the `viewer` allowance from the CHECK constraint after the rollback window.

**Rollback:** before step 5, `alembic downgrade 0013` is lossless for roles and requires `-x audit_export=<file>` if audit entries exist, then redeploy the p21/p22 images. After step 5, export the audit log first, because downgrade maps `superadmin→admin`. As a last resort, restore the pre-migration backup into a separate database. Never use `docker compose down -v`.

## 13. Remaining risks and notes

- **No superadmin exists until step 5.** After migration, nobody can manage accounts or read the audit log until the CLI is run. The existing `admin` keeps all ML capabilities but cannot manage users (D4).
- **`origin/main` carries a stray commit `8c846b7`** (v2 tests alongside old app code) from a branch mix-up. It is harmless until `feature/rbac-v2` is merged. History was not rewritten and nothing was force-pushed.
- **Current production `.env`** has `APP_VERSION=0.5.0-p22` and `PASSWORD_REHASH_ON_LOGIN=false`; both need review at deployment time. The live admin password has not been rotated.
- `ml_engineer` is treated as `user` by the legacy reader, and migration refuses to guess. There are none in production today.
- Audit `before`/`after` of an empty value is stored as JSON `null`, not SQL NULL.
- The CLIs ran only in unit tests and on the disposable stack, never on production.

## 14. Awaiting approval

Per instructions, work stops here. Needed from you, separately:
1. Approval to run migration 0014 on production, and the deployment of the `0.6.0-rc1` images.
2. **The explicit account** to become superadmin (D6) and whether it is the existing admin (`--promote`) or a new account. I will not select one.
3. Whether to merge `feature/rbac-v2` and how to handle `8c846b7` on `origin/main`.
