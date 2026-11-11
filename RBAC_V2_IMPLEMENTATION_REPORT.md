# RBAC V2 Implementation Report

**Branch:** `feature/rbac-v2` (images built from `531b99e`; release-readiness review in §12–15) · **Release candidate:** `0.6.0-rc1`
**Status:** implemented and verified in isolated environments only; **not yet ready to deploy** (open items in §12.6). **Nothing has been applied to production.**

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

## 12. Release-readiness review (2026-11-11)

Review-only. No production change, merge, push, deployment, migration, bootstrap or recovery run was
made. Tests ran only on a throwaway PostgreSQL 18 container (tmpfs, removed afterwards), SQLite, an
unpacked `git archive` of `origin/main` (deleted afterwards) and a no-database probe of the P21 image.
Production was re-checked afterwards: all `aiproject-*` containers still run the p21 images, healthy.

### 12.1 Branch topology (items 1–3)

| Fact | Value |
|---|---|
| `feature/rbac-v2` | `daacd5b` (this report), local **and** `origin/feature/rbac-v2` are identical |
| `origin/main` = local `main` | `8c846b7` |
| Merge base | `b79252d` ("docs: add RBAC v2 audit and implementation plan report") |
| `8c846b7` parent | `b79252d` (single parent, one commit ahead of the base) |
| `8c846b7` ancestor of `feature/rbac-v2`? | **No.** The branches diverged at `b79252d` |
| Commits only on feature | 24 |
| Commits only on main | 1 (`8c846b7`) |

**Correction to my earlier hand-off:** I said the feature branch was not pushed. It already exists on
`origin` at `daacd5b` (pushed by your tooling). Nothing in this review pushed anything.

**`8c846b7`** (Mehak-991, 2026-11-11 14:06 +0530, "test: add unit tests for admin bootstrap, RBAC, and
auth helpers") touches four files only: `tests/helpers.py` (+35), `tests/unit/test_admin_bootstrap.py`,
`tests/unit/test_auth_rbac.py`, `tests/unit/test_registration_rbac.py` (+209 / −244 in total). It
contains **no application code**. It is the set of RBAC-v2 tests I restored after the working tree was
switched to `main` mid-work, committed on `main` by your tooling.

**Overlap with the feature branch:** exactly those four files.
- The three `test_*.py` files are **byte-identical** on both branches.
- `tests/helpers.py` differs by 25 lines: the feature side adds `iter_api_routes` after the same `insert_account`.
- A trial merge (`git merge-tree`, no refs touched) reports **one conflict**, in `tests/helpers.py` (both sides appended at the end of the file). Everything else merges cleanly.

**`origin/main` is currently red.** Its tests expect RBAC v2 behaviour but its application code is the
old code. Run in an unpacked copy of `origin/main`: `test_admin_bootstrap`, `test_auth_rbac`,
`test_registration_rbac` give **6 failed, 10 passed, 29 errors** (login returns 500 because the old
`UserRead` rejects the role `user`). So `main` should not be tagged or built until the feature is merged.

**Recommended integration (history-preserving, no rewrite, no force-push):**
1. Merge with a **true merge commit**: `git switch main` → `git merge --no-ff feature/rbac-v2`. Never rebase or squash, so `8c846b7` and all 24 feature commits stay reachable and the pushed `feature/rbac-v2` stays valid.
2. Resolve the single `tests/helpers.py` conflict by **keeping the feature side** (it is a strict superset: identical `insert_account` plus `iter_api_routes`). The other three files are identical, so the merged tree should equal the feature tree.
3. Before pushing, check `git diff feature/rbac-v2 HEAD` is empty and re-run the unit and PostgreSQL integration suites on the merge result. The image inputs are unchanged from `531b99e`, so `0.6.0-rc1` stays valid for the merged tree.
4. Push `main` as a fast-forward of the merge commit (normal push, no `--force`); tag the release at the merge commit. A GitHub pull request (merge-commit method) achieves the same and also runs CI.
5. Do this **before** the production deployment so the deployed image has a commit on `main`. It needs your separate approval.

### 12.2 Verification of the safety properties (items 4–6, 10)

| Check | Evidence this review | Result |
|---|---|---|
| Migration 0014 and its rollback | `tests/integration/test_rbac_migration.py` (10 tests: mapping, no promotion, constraint and default, downgrade, guarded downgrade, repeat upgrade) + PostgreSQL test of the real migration, plus the earlier restored-backup rehearsal | PASS |
| Unmapped `ml_engineer` aborts | `test_an_unmapped_ml_engineer_aborts_and_changes_nothing`, `test_an_unknown_role_value_aborts`, explicit `-x ml_engineer=user\|admin` audited; rehearsal showed the database unchanged | PASS |
| Every route covered; unregistered routes fail closed | `test_every_registered_route_declares_a_policy`, `test_a_route_with_no_declared_policy_is_refused_for_everyone`, `test_the_matrix_covers_exactly_the_routes_the_app_serves`, and the 70-pair table in §4 | PASS |
| Last-superadmin concurrency | `test_rbac_pg.py`: mutual demotion, ring of five, concurrent deactivate/demote, simultaneous bootstrap, concurrent registrations, on real PostgreSQL | PASS |
| Audit immutability | PostgreSQL triggers `audit_logs_no_change` / `audit_logs_no_truncate`; UPDATE, DELETE, TRUNCATE rejected (earlier on the disposable stack, and in the PG migration test) | PASS |
| Registration defaults | `test_registration_rbac.py`, `test_concurrent_public_registrations_never_produce_a_privileged_account`: no role field; always `user` | PASS |
| Bootstrap safeguards | `test_cli_superadmin.py` (16 tests): one-time, refuses before 0014, never picks an account, promotion needs typed confirmation, no password echoed | PASS |
| Isolated test run | Integration suite **36 passed** on a PostgreSQL migrated to head 0014; RBAC unit files plus the integration directory passed in the same session | PASS |

An early run in this review showed 4 errors in `test_job_recovery_pg.py` ("relation jobs does not
exist"). That was my test setup (a fresh PostgreSQL that had not been migrated), not a product fault;
after `alembic upgrade head` all 36 integration tests passed. The full unit suite was not re-run: only
documentation changed since the last full run (724 passed, 1 skipped).

### 12.3 Deployment sequence defect found and fixed (item 7)

My earlier sequence (deploy v2 on revision 0013 first, migrate and bootstrap afterwards) has a real gap:
- Account management belongs to `superadmin` only (D4), so from the moment v2 code serves traffic **nobody can manage accounts**.
- `create_superadmin.py` refuses before migration 0014 (by design, it needs `audit_logs`), so a superadmin cannot be established until the migration has run.
- Between "v2 started" and "bootstrap finished" the system is therefore up with no way to manage accounts.

The sequence in §14 closes the gap by never serving v2 traffic until a superadmin exists: the
application and worker are stopped, the database is migrated and the superadmin created with one-off
containers, and only then is v2 started. The "expand" phase (v2 code on 0013 with
`RBAC_STORE_LEGACY_VIEWER=true`) is **not** used for this deployment; it stays available as a
documented option but it is what creates the gap, and it does not make a P21 rollback safer (§12.4).

### 12.4 P21 compatibility and exact rollback limitations (item 8)

Probe run inside the real P21 image (`aiproject-backend:0.5.0-p21`, no database, nothing persisted):

| Stored role | `UserRead` (used by `/auth/me`, `/auth/users`, register, update) | Role-gated "viewer" route | Admin route | `is_admin` |
|---|---|---|---|---|
| `viewer` | ok | allowed | 403 | false |
| `admin` | ok | allowed | allowed | true |
| `user` | **ValidationError → HTTP 500** | **403** | 403 | false |
| `superadmin` | **ValidationError → HTTP 500** | **403** | 403 | false |

Reading the P21 source: `UserRole = Literal["admin","ml_engineer","viewer"]`; `require_role` is an
exact string match; ownership helpers test `role == "admin"`. Consequences if P21 runs against a
database that still holds `user` or `superadmin`:
- Login still succeeds (the token response has no role field) but `/auth/me` fails with 500 for those accounts, and **`GET /auth/users` fails with 500 for the whole list as soon as one such account exists**, which also breaks the P21 admin's user screen.
- `user` accounts get 403 on every role-gated route (including read-only ones); a `superadmin` gets 403 everywhere and is not treated as admin, so it loses even its former admin access.
- P21 cannot verify Argon2id hashes (its `CryptContext` is PBKDF2 and bcrypt only). If `PASSWORD_REHASH_ON_LOGIN=true` has converted any hash under v2, those users **cannot log in** after a rollback to P21.

Therefore:
1. **P21 must never be started against a 0014 database.** The only safe states for P21 are revision 0013 with only `admin`/`viewer`/`ml_engineer` roles.
2. Rollback after migration needs the roles mapped back first: `alembic downgrade 0013` (`user→viewer`, `superadmin→admin`) with `-x audit_export=<new file>` (audit entries are dropped from the database and kept only in that file).
3. The downgrade is **not lossless**: `superadmin` and `admin` become indistinguishable; accounts created or changed after the migration come back as `viewer`/`admin` regardless of intent; an `ml_engineer` that was mapped with `-x` does not return to `ml_engineer`; the audit log table disappears.
4. **Standing rule conflict:** your rules forbid an Alembic downgrade on production. Rollback therefore means either (a) restoring the pre-migration backup into a separate database and pointing P21 at it, which loses every write made after the backup (new accounts, jobs, predictions, deployments), or (b) your explicit, separate approval for the downgrade. Decide which before the window opens.
5. Keep `PASSWORD_REHASH_ON_LOGIN=false` until the rollback window has closed; otherwise a rollback strands rehashed users.
6. Because rollback is destructive in both forms, the window should be short and the verification in §14 complete before reopening to users.

### 12.5 Password rotation prerequisite (item 9)

**Status: PENDING. Not verified, and I cannot verify it.** The live admin password was not rotated as of
the last preflight, and nothing since then shows otherwise. I did not read `.env` values or try any
credential. I will treat it as done only when you confirm that you rotated it yourself, through your
own channel, and that the old password no longer works; I should not be given the password to check.
Deployment is blocked on this item, along with the checklist below.

### 12.6 Release-readiness checklist

| # | Item | Status |
|---|---|---|
| 1 | RBAC v2 code complete on `feature/rbac-v2` (`daacd5b`) | ✅ |
| 2 | Unit (724) and integration (36) tests pass on isolated databases | ✅ |
| 3 | Route policy coverage and deny-by-default proven | ✅ |
| 4 | Migration 0014 upgrade, downgrade, abort conditions proven on SQLite, PostgreSQL and a restored real backup | ✅ |
| 5 | Concurrency, audit immutability, registration and bootstrap safeguards proven | ✅ |
| 6 | Candidate images `0.6.0-rc1` built from `531b99e`, not deployed | ✅ |
| 7 | P21 and p22/0.5.1 rollback images preserved | ✅ |
| 8 | Deployment sequence without a no-superadmin interval | ✅ designed (§14), not yet executed |
| 9 | `main` red until the feature merge (`8c846b7`) | ⛔ resolve by merge (§12.1) |
| 10 | Feature merged into `main`, pushed, tagged | ⏳ needs your approval |
| 11 | Admin password rotation independently confirmed | ⏳ **PENDING** |
| 12 | Superadmin account named by you (D6), and new-vs-promote chosen | ⏳ needs your decision |
| 13 | Rollback method chosen: backup restore (default) or approved downgrade | ⏳ needs your decision |
| 14 | Fresh verified production backup immediately before the window | ⏳ at deployment |
| 15 | Production `.env` values reviewed and updated at the window (§14, step 3) | ⏳ needs your approval |
| 16 | Written go-ahead for the production migration and deployment | ⏳ |

## 13. Unresolved risks

| Risk | Severity | Mitigation / owner |
|---|---|---|
| Admin password rotation not independently confirmed | High (blocks deploy) | You rotate and confirm (§12.5) |
| Rollback after migration is destructive either way (restore loses later writes; downgrade merges roles and drops audit rows) and downgrade is barred by standing rule | High | Short window, fresh backup, decide method up front (§12.4) |
| P21 mis-handles `user`/`superadmin` (500s, 403s, admin list failing) | High if P21 is ever started on 0014 | Never run P21 against 0014; follow §12.4 |
| `PASSWORD_REHASH_ON_LOGIN=true` would strand users on rollback | Medium | Keep `false` until the rollback window closes |
| `main` red until merge; `8c846b7` on `origin/main` without app code | Medium | Merge commit per §12.1 |
| Production `.env` has `APP_VERSION=0.5.0-p22` (value reported by earlier preflight; not re-read now) and must be set to `0.6.0-rc1`; `RBAC_STORE_LEGACY_VIEWER` left unset (false) | Medium | Change only inside the approved window |
| After migration no one can manage accounts until the CLI runs | Medium | Run it inside the window before starting v2 (§14) |
| The single existing `admin` loses user management (D4, `superadmin` only) | Low (by design) | Promote that account, or create a new superadmin: your decision (D6) |
| `/metrics` and `/health` are unauthenticated routes in the app (unchanged from before) | Low | Keep them off the public edge as in the existing Nginx setup |
| Audit `before`/`after` of an empty value stored as JSON `null` | Low | Cosmetic |

## 14. Exact production deployment sequence (NOT to be run until separately approved)

All commands run from the project directory with the production compose file and `.env.production`.
Never `docker compose down -v`; never touch volumes; keep the `pre-p21`, `0.5.0-p21` and `0.5.1` images.

**A. Before the window (no production change)**
1. Merge `feature/rbac-v2` into `main` as in §12.1; confirm tests green on the merge result and `git diff feature/rbac-v2 HEAD` is empty.
2. You confirm the admin password was rotated (§12.5) and name the superadmin account (D6): either a **new** email (the CLI creates it and prompts for a password) or the **existing** admin email via `--promote`.
3. You choose the rollback method (§12.4, item 4).
4. Prepare the `.env.production` edit (do not apply yet): `APP_VERSION=0.6.0-rc1`, `PASSWORD_REHASH_ON_LOGIN=false`, leave `RBAC_STORE_LEGACY_VIEWER` unset. Confirm backend and frontend images `0.6.0-rc1` are present (`d8e5d5baf6cb`, `19b123ad0a4a`).

**B. Window**
1. **Backup:** take a fresh database backup with the existing script; verify checksum; restore it into a *separate disposable* database and confirm row counts and revision `0013`.
2. **Stop traffic:** stop `frontend`, `app` and `worker` (leave `db` running). Record the container list.
3. **Apply the `.env.production` edit** from A4.
4. **Dry-run the plan:** `alembic current` (expect `0013`); `alembic heads` (expect `0014`); list roles (expect only `admin`/`viewer`; if any `ml_engineer` exists, stop and ask for `-x ml_engineer=user|admin`).
5. **Migrate (one-off container, `--no-deps`, v2 image):** `alembic upgrade 0014`. Expect it to end at `0014`; roles `admin` stays `admin`, `viewer → user`; zero superadmins.
6. **Bootstrap the superadmin before any v2 traffic** (one-off container, `--no-deps`, v2 image): `python scripts/create_superadmin.py --email <named account>` (password via `-it` prompt or `BOOTSTRAP_SUPERADMIN_PASSWORD`), or add `--promote` and type the email to confirm. Unset the password variable afterwards.
7. **Verify in the database:** exactly one active `superadmin`; revision `0014`; audit rows for the role mappings and the bootstrap; user and resource counts equal to the backup.
8. **Start v2:** `up -d --no-deps app worker frontend` with `0.6.0-rc1`. Wait for healthy.
9. **Verify:** `scripts/check_stack.py`; `scripts/e2e_check.py` with the superadmin credentials supplied through environment variables; sign in as the superadmin in the browser and check Users, Audit Logs and Settings; sign in as a `user` and as the `admin` and check their limited views; confirm public registration creates only a `user`; read the audit log.
10. **Go / no-go:** if any check fails, roll back (below) before reopening to users.

**C. Rollback (decided in A3)**
- *Default, backup restore:* stop `frontend`, `app`, `worker`; restore the verified backup into a **separate** database; revert `.env.production`; start the P21 images (`aiproject-backend:0.5.0-p21`, `aiproject-frontend:0.5.0-p21`) against that database. All writes after the backup are lost; the 0014 database is kept untouched for later analysis.
- *Only with your explicit approval:* `alembic downgrade 0013 -x audit_export=<new file>` then P21 images (§12.4 for the data consequences).

**D. After the window**
- Keep `PASSWORD_REHASH_ON_LOGIN=false` until the rollback window closes, then enable it deliberately.
- Later release (contract): remove the `viewer` allowance from the CHECK constraint and the legacy reader.

## 15. Awaiting approval

Work stops here; nothing below has been done. I need from you, separately:
1. Approval to merge `feature/rbac-v2` into `main` (merge commit, no force) and push, or tell me to open a pull request instead.
2. Independent confirmation that the admin password was rotated.
3. The account to become superadmin, and whether it is new or the existing admin (D6).
4. The rollback method (backup restore or an approved downgrade).
5. Written approval for the production backup, migration, bootstrap and deployment window in §14.
