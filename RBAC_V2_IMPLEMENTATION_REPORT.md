# RBAC v2 Implementation Report (audit and plan)

AIProject, 2026-11-11. **Status: read-only audit and implementation plan. No application code, database,
migration, configuration or container was changed, and nothing was deployed.** This document is the
deliverable for the audit step; the sections that need implementation evidence (security test results)
are marked as such and will be filled in after you approve the plan.

## 0. Decisions needed before implementation

The audit found gaps between the specification and the codebase. Each needs an explicit answer; my
recommendation is marked.

| # | Question | Why it matters | Options (recommended in bold) |
|---|---|---|---|
| D1 | **There is no "candidate record" entity in this project.** | The spec's core rules (admin/user rights over candidate records, "Candidate list", "Add/Edit/Delete candidate") have nothing to attach to today: no table, API, schema or UI. The only `candidate` hits are unrelated (experiment candidate models). | **A. Build a new `candidates` entity** (table, CRUD API, UI). Needs your field list; the sample data suggests placement-prediction features (age, experience_years, study_hours, attendance, outcome) plus name/contact. B. Treat uploaded dataset rows as candidates (no row-level CRUD exists; large redesign). C. Do not build candidates; apply the three roles to the existing resources only (datasets, models, experiments, jobs, predictions). |
| D2 | What may `admin` do with ML resources (upload dataset, train, experiments, jobs, drift analysis, deploy)? | Today's `admin` can do all of it. A literal reading of the spec gives these to `superadmin` only, which would silently remove capabilities from the current admin. | **P2 (preserve): `admin` keeps these; `superadmin` additionally owns users, roles, audit logs, settings.** P1 (literal): ML operations are superadmin-only. |
| D3 | May `user` (read-only) run predictions, explanations and NLP helpers? | Today every role can. They are POSTs but change no managed record (they write a prediction log). | **Allow, as "read-class" actions.** Deny (strictly read-only; breaks the current viewer experience). |
| D4 | May `admin` manage ordinary `user` accounts? | Spec forbids admins managing admin accounts and says nothing about plain users. | **No: user management is superadmin-only.** Allow admin to create/deactivate `user` accounts only. |
| D5 | How to roll out safely? | Old code (p21/p22/0.5.1) cannot read roles `user`/`superadmin`, so a data migration makes a code rollback unsafe. | **Expand, migrate, contract** (section 7). Single-step migration. |
| D6 | Who becomes the first `superadmin`? | The migration must not promote anyone. | **Explicit CLI after migration**, naming an existing account or a new one (section 6). I will not choose for you. |
| D7 | User deletion: soft or hard? | No delete endpoint exists today ("deletes where safe"). All FKs to `users` are `SET NULL` (and refresh tokens `CASCADE`), so deletion is technically safe but loses attribution. | **Deactivate by default; hard delete only for accounts that own nothing, with an audit entry.** Hard delete always. |

## 1. Existing RBAC architecture (as audited)

**Roles:** `viewer`, `ml_engineer`, `admin`, stored as a plain `users.role VARCHAR(32) NOT NULL`
(server default `'viewer'`, index `ix_users_role`). There is **no CHECK constraint and no trigger** on
`users`, so any string can be stored; the API restricts it only with a Pydantic `Literal`
(`app/schemas/auth.py:7`). The frontend duplicates the list (`frontend/src/types/auth.ts`).

**Enforcement.**
- `require_role(*roles)` in `app/api/deps.py` is a per-endpoint FastAPI dependency (403 with a message
  naming the roles). Authentication is `get_current_user`: it decodes the JWT, loads the user **from the
  database on every request**, and rejects missing or inactive users (401). The `role` claim inside the
  JWT is informational and is **not** used for authorization, so role changes take effect immediately.
- Object-level rules live in `app/services/authorization.py`: `admin` sees and uses everything;
  other roles see objects they own, ownerless legacy objects, and prediction logs they requested.
- Registration (`auth_service.register_user`): public requests always get `viewer`; asking for another
  role returns 403 unless the caller is an admin. The payload still accepts a `role` field.
- Role changes (`update_user_by_admin`): admin-only; protects the last active `admin` (cannot demote or
  deactivate it); deactivation revokes the account's refresh tokens. **No audit record is written.**
- First admin: explicit CLI `scripts/create_admin.py` (Phase 22).

**Gaps relative to the spec:** deny-by-default is by convention only (a new route with no dependency is
public); no `superadmin` tier; no audit log (the word "audit" in the code means prediction logging); no
user create or delete endpoint apart from `register`; no profile update; no "system settings" backend
(the UI tab only displays runtime information); the last-admin check is not race-safe.

**Live data (read-only counts, 2026-11-11):** 3 users: `admin` 1, `viewer` 2, `ml_engineer` 0; all
active. The foreign keys to `users` are `datasets.owner_id`, `ml_models.owner_id`,
`experiments.created_by_id`, `jobs.created_by_id`, `prediction_logs.requested_by_id` (all
`ON DELETE SET NULL`) and `refresh_tokens.user_id` (`CASCADE`).

**Current endpoint guards (derived from the running application, 63 endpoint/method pairs):** 7 public,
1 optional-auth (`register`), 34 any authenticated role, 4 `admin`, 17 `admin` or `ml_engineer`.
Frontend role logic is confined to `App.tsx`, `UserManagementPage.tsx`, `ExperimentTrackingPage.tsx`,
`DataDriftMonitoringPage.tsx` and `types/auth.ts`. Tests: 62 occurrences of `viewer`, 14 of
`ml_engineer`, 53 of `"admin"` across 14 files need updating (mechanical).

## 2. Proposed roles and permission matrix

S = superadmin, A = admin, U = user. Recommended choices D2 to D4 assumed.

| Capability | S | A | U |
|---|---|---|---|
| View candidate records, details, dashboard data, reports | yes | yes | yes |
| Create candidate records | yes | yes | no |
| Update candidate records (any, including other admins') | yes | yes | no |
| Delete candidate records (any) | yes | yes | no |
| Run predictions, explanations, NLP helpers (read-class) | yes | yes | yes |
| Upload datasets, train models, experiments, jobs, drift analysis, deploy/undeploy | yes | yes (D2) | no |
| Manage own profile / change own password | yes | yes | view profile, change own password |
| View users | yes | no | no |
| Create, deactivate, delete user accounts | yes | no | no |
| Assign or revoke `admin` / `user` | yes | no | no |
| Grant or revoke `superadmin` | yes (only an existing superadmin) | no | no |
| Audit logs, security settings, RBAC policy, system settings | yes | no | no |

Invariants enforced in one place (a `change_role` service, not per endpoint): only a superadmin
changes roles; no one changes their own role or active flag; the last active superadmin can never be
demoted, deactivated or deleted (checked under a row lock so two concurrent requests cannot both
succeed); public registration always yields `user` and its payload no longer has a `role` field;
every role or status change writes an audit record in the same transaction.

## 3. Authorization design (centralised, deny-by-default)

- New `app/core/permissions.py`: `Role` enum, `Permission` enum (`candidate:read`, `candidate:create`,
  `candidate:update`, `candidate:delete`, `ml:operate`, `ml:predict`, `users:read`, `users:manage`,
  `roles:assign`, `audit:read`, `settings:manage`, ...), and one `ROLE_PERMISSIONS` table. `superadmin`
  holds every permission. This table is the single source of truth.
- New dependency `require_permission(Permission.X)` replaces `require_role(...)`. A global policy
  dependency on the `/api/v1` router **denies any route that declares neither a permission nor an
  explicit `@public` marker** (deny-by-default at runtime, not just by convention).
- 401 for missing, invalid or inactive credentials (unchanged); 403 for authenticated callers without
  the permission, with a stable error code.
- `GET /auth/me` and the login response gain `permissions: [...]` computed on the server; the frontend
  uses that list, so UI and API cannot drift apart.
- Object-level helpers (`authorization.py`) treat `superadmin` and `admin` as unrestricted and keep the
  current ownership scoping for `user`.
- Database defence in depth: a `CHECK (role IN ('user','admin','superadmin'))` constraint after the data
  migration.

## 4. API endpoint permission mapping

Current guard to proposed policy. "any" = any authenticated role today. New endpoints are marked **new**.

| Endpoint(s) | Current | Proposed |
|---|---|---|
| `GET /`, `GET /health`, `GET /api/v1/health` | public | public (explicit marker) |
| `GET /metrics` | public, optional token | unchanged (token-gated, not exposed by nginx) |
| `POST /auth/login`, `/auth/refresh`, `/auth/logout` | public | public (explicit marker) |
| `POST /auth/register` | optional-auth, accepts `role` | public; always creates `user`; `role` removed from the payload |
| `GET /auth/me`, `POST /auth/change-password` | any | S, A, U (own account; `/me` adds `permissions`) |
| **new** `PATCH /auth/me` (own display name) | none | S, A, U |
| `GET /auth/users` | admin | S only |
| `PATCH /auth/users/{id}` (role, status, name) | admin | S only, via `change_role` rules; audited |
| **new** `POST /auth/users` (create with role `admin`/`user`) | none | S only; audited; can never create `superadmin` |
| **new** `DELETE /auth/users/{id}` | none | S only; refused for the last superadmin and for accounts that own records unless deactivated first |
| **new** `POST /auth/users/{id}/superadmin`, `DELETE ...` (grant / revoke) | none | S only; audited |
| **new** `GET /audit-logs` | none | S only |
| **new** `GET /system/settings` (non-secret runtime values) | none | S only (read-only; writes are out of scope) |
| **new** candidates: `GET /candidates`, `GET /candidates/{id}` | none | S, A, U |
| **new** candidates: `POST`, `PUT`, `PATCH`, `DELETE` | none | S, A (any record, per spec) |
| Datasets: `GET /datasets`, `/{id}`, `/{id}/summary` | any | S, A, U (U scoped as today) |
| Datasets: `POST /datasets`, `POST /datasets/validate` | admin, ml_engineer | S, A |
| Models: `GET /models`, `/models/{id}`; deployments `GET` (2) | any | S, A, U |
| Models: `POST /models/train` | admin, ml_engineer | S, A |
| Models: `POST /models/{id}/deploy`, `/undeploy` | admin | S, A (D2) |
| Predict and explain: `POST /models/{id}/predict`, `/explainability/shap`, `/lime`, `POST /nlp/classify`, `/embeddings`, `/tokens/count`; `GET /ai/status` | any | S, A, U (D3) |
| Explainability reads (`summary`, `feature-importance`) | any | S, A, U |
| `POST /llm/chat`, `POST /nlp/analyze` | admin, ml_engineer | S, A |
| Experiments: `GET` list, `/compare`, `/{id}` | any | S, A, U |
| Experiments: `POST` create, `/run`, `/cancel`, `/rerun` | admin, ml_engineer | S, A |
| Jobs: `GET` list, `/metrics`, `/{id}`, `/{id}/result` | any | S, A, U |
| Jobs: `POST` submit, `/cancel`, `/retry` | admin, ml_engineer | S, A |
| Drift: `GET` overview, alerts, reports | any | S, A, U |
| Drift: `POST /alerts/{id}/resolve`, `analyze-quality`, `analyze-drift`, `analyze-performance` | admin, ml_engineer | S, A |
| Monitoring `GET` (2); predictions history `GET` (3) | any | S, A, U (U scoped as today) |
| `POST /predictions/history/{id}/ground-truth` | admin, ml_engineer | S, A |

With D2 answered "literal" (P1), every row marked "S, A" for ML operations becomes "S only".

## 5. Frontend changes

- `types/auth.ts`: `UserRole = 'user' | 'admin' | 'superadmin'`; `permissions: string[]` on the user.
  A small `usePermission()` helper reads the server-provided list. All checks of the form
  `user?.role === 'admin'` or `'ml_engineer'` are replaced.
- Navigation by permission: **user** sees Dashboard (existing monitoring overview), Candidate list and
  read-only details, Reports (existing drift and monitoring reports); **admin** adds Candidate
  management (add, edit, delete) and the ML pages it keeps under D2; **superadmin** adds User
  Administration, Role management, System Settings (read-only view), Audit Logs.
- New pages: Candidates (list, detail, add, edit, delete; only if D1 = A) and Audit Logs. User
  Administration gains role assignment limited to what the backend allows, without the ML Engineer
  option, and with grant/revoke superadmin.
- Registration text already says new accounts are viewers; it becomes "User (read-only)".
- Hiding a control is cosmetic only; every action is re-checked by the backend. The existing static
  frontend tests are extended to forbid role-string comparisons in components.

## 6. Superadmin bootstrap and recovery

- **No API ever creates or grants superadmin to the public.** Only an existing superadmin can grant
  or revoke it (audited).
- **One-time bootstrap CLI** `scripts/create_superadmin.py`, run with server access (the same model
  as `create_admin.py`): `--email` for a new account, or `--promote EMAIL` for an explicit existing
  account (never inferred), password from `BOOTSTRAP_SUPERADMIN_PASSWORD` or a hidden prompt, never
  printed. It refuses when an active superadmin already exists. It writes an audit entry (actor
  `cli`). The migration itself never promotes anyone.
- **Recovery** when every superadmin is lost: the same CLI works again because no active superadmin
  exists. If one exists but its password is lost: `scripts/reset_password.py --email ...` (server
  access, audited). Because the last-superadmin guard applies to every API path, the only way to reach
  zero is direct database edits, which the CLI recovers from.
- After the migration and before the new UI is used, an operator must run the bootstrap once (D6);
  the deployment order in section 7 includes it.

## 7. Database migration plan (not run)

**Schema changes, new Alembic revision `0014` (no data loss, no table rewrite of user data except the
role column):**
1. Create `audit_logs` (id, created_at, actor_user_id FK `SET NULL`, actor_email snapshot,
   action, target_user_id FK `SET NULL`, target_email snapshot, before JSONB, after JSONB, request_id,
   ip, detail). Append-only by design (no update or delete code path; a PostgreSQL trigger can
   enforce it).
2. Change the `users.role` server default from `'viewer'` to `'user'`.
3. Data update per the mapping below.
4. Add `CHECK (role IN ('user','admin','superadmin'))` (named `ck_users_role`) after the update.
5. Keep `ix_users_role`. Passwords, tokens, ownership columns and all other tables are untouched.

**Legacy role mapping (explicit, nothing silently promoted):**

| Legacy role | Live count | New role | Rule |
|---|---|---|---|
| `viewer` | 2 | `user` | one-to-one, same permissions class (read-only) |
| `admin` | 1 | `admin` | retains admin access; **not** promoted to superadmin |
| `ml_engineer` | 0 | none by default | **the migration aborts with a clear message listing the count unless the operator passes an explicit mapping** (`alembic -x ml_engineer=user` or `-x ml_engineer=admin`), recorded in the audit log. Nobody is promoted without that explicit choice |
| (any other value) | 0 | none | migration aborts |

Because the live database has no `ml_engineer` rows, the live run needs no mapping decision. After
the migration no superadmin exists until the bootstrap CLI is run (section 6).

**Safe rollout (D5, expand, migrate, contract):**
1. *Expand:* ship code that reads both vocabularies (`viewer` is treated as `user`, no `superadmin`
   rows yet) and still works against the current data. Rolling back to the previous release stays safe.
2. *Migrate:* back up, run revision `0014` on a copy first, then live; run the bootstrap CLI.
3. *Contract:* new roles are authoritative; remove the legacy reader in a later release.

Verification for each stage: row counts and password hashes unchanged, the three roles present, no
`viewer`/`ml_engineer` left, constraint valid, audit table empty, application login working.

## 8. Rollback strategy

- **Before the migration (expand stage):** roll back the images only (`pre-p21`, p21, `0.5.0-p22` and
  `0.5.1` all remain). Old code keeps working because the data is unchanged.
- **After the migration:** old releases cannot read `user` or `superadmin` and would fail validation
  for those accounts. Preferred rollback is **not** a downgrade: restore the pre-migration dump into
  a new database and point `DATABASE_URL` at it (never overwrite the live one). A tested `downgrade()`
  is still provided, mapping `user` to `viewer` and `superadmin` to `admin`, dropping the CHECK and the
  default change, and exporting `audit_logs` to a file before dropping it. It will be exercised only on
  a disposable database. A downgrade collapses the superadmin/admin distinction, so a restore is
  safer.
- Every step requires a fresh verified backup first (the recipe from the Phase 22 report).

## 9. Security test plan and results

**Results so far: no new tests exist yet.** Baseline on the current code: 613 passed, 1 skipped. The
tests below will be written first and run in the existing suite and on a throwaway PostgreSQL.

| Spec requirement | Test |
|---|---|
| User cannot POST, PUT, PATCH or DELETE candidate records | parametrised over all four methods and every candidate route: 403 (401 unauthenticated) |
| Admin can create, update and delete records belonging to any administrator | records created by admin A are updated and deleted by admin B; and by a superadmin |
| Admin cannot change roles | `PATCH /auth/users/{id}` with each role value, self and others: 403 |
| Admin cannot access superadmin-only endpoints | every superadmin-only route returns 403 for admin and user |
| Superadmin can perform all authorised operations | full matrix run as superadmin |
| Public registration always creates `user` | payloads with and without `role`; a `role` field is now a 422 |
| No user can self-assign admin or superadmin | registration, `PATCH /auth/me`, and the user-update route as every role |
| Last superadmin cannot be removed | demote, deactivate, delete, self-demote, and two concurrent attempts on PostgreSQL |
| Unauthorised direct API requests return correct codes | 401 for no/invalid/inactive credentials, 403 for insufficient role, on every route |
| Deny-by-default | a test walks every route in the running app and fails if one lacks a declared policy; a route added without a marker returns 403 |
| Policy table | each role's permission set equals the matrix in section 2 |
| Audit | every role change, creation, deactivation, deletion and bootstrap writes one record with actor, target, before and after |
| Migration | on a copy of production-shaped data: mapping, aborts for `ml_engineer` without a mapping, passwords and relationships preserved, idempotent re-run, downgrade on a disposable database |
| Frontend | static guards against role-string checks; a built-bundle check for the removed role names |

The existing role-dependent tests (14 files) are migrated mechanically and not weakened.

## 10. Proposed implementation steps (after approval)

1. Answer D1 to D7 (and the candidate field list if D1 = A).
2. Policy module, deny-by-default dependency, `change_role` service, audit table, and the tests above,
   in a feature branch. No schema change is applied anywhere yet.
3. Revision `0014` and its tests on a disposable PostgreSQL.
4. Candidate entity (if D1 = A): model, revision, CRUD routes, tests.
5. Frontend (`permissions`, navigation, pages) and its static tests.
6. Bootstrap CLI, reset CLI and documentation.
7. Build candidate images under a new tag; run the full suite, PostgreSQL integration tests and a
   rehearsal of the migration on a restored copy of the live backup. **Stop for your approval before
   any production step.**

## 11. What this audit did not do

No migration or code change was made; no production data was touched; no test was added; the live
stack, `.env`, volumes and rollback images are as they were. The endpoint table in section 1 was
derived from the running application's real dependency graph, not from reading source alone.
