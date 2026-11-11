# Release Notes

## 0.6.0 (release candidate; not deployed to production)

Version string in the code: `0.6.0`. Candidate image tags: `0.6.0-rc1` (RBAC v2 only) and `0.6.0-rc2`
(adds the items below, built from commit `321babd` for disposable testing). **Final release images
must be rebuilt from the merged commit and re-verified before use.**

### Upgrade impact — read first

* Requires migration `0014` (RBAC v2 roles and the `audit_logs` table) and creates **no** superadmin:
  after migrating, create one on the server with `scripts/create_superadmin.py`. Until then nobody can
  manage accounts or read the audit log.
* Roles change from `admin` / `ml_engineer` / `viewer` to `user` / `admin` / `superadmin`. `viewer`
  becomes `user`, `admin` stays `admin`; the migration aborts if an `ml_engineer` account exists
  unless you map it explicitly (`-x ml_engineer=user|admin`).
* User and role management is now **superadmin only**. An existing `admin` keeps all ML capabilities
  but loses account management.
* The previous release (`0.5.0-p21`) cannot read the new roles or Argon2id hashes. Roll back by
  restoring the pre-migration backup into a separate database, not by downgrading.
* `ALLOW_FIRST_USER_ADMIN` no longer exists (public registration never creates a privileged account).
* `APP_VERSION` is required by Compose (no default). New optional variables:
  `RBAC_STORE_LEGACY_VIEWER`, `PASSWORD_REHASH_ON_LOGIN` (both default `false`; see `.env.example`).

### Added

* Three-role RBAC with a central permission registry, deny-by-default routes and permissions
  returned by `GET /auth/me`.
* Append-only audit log (database triggers) and `GET /api/v1/audit-logs` (superadmin).
* Server-side `scripts/create_superadmin.py` and `scripts/reset_password.py`.
* Superadmin user administration, including guarded deletion and superadmin grant/revoke.
* Dataset **row preview**: `GET /api/v1/datasets/{id}/preview` and a "Data Preview" tab.
* **Gradient boosting** and **decision tree** algorithms for models and experiments.
* **Cross-validation** (5-fold, training+validation rows only) in `training_metadata`, shown in the
  model detail view.
* **My Profile** page: display name and password change (signs out all sessions).
* Argon2id password hashing with optional rehash on login.

### Changed

* CI runs the full Ruff configuration (including security rules) and frontend lint; the integration
  job migrates the database first; compose validation supplies `APP_VERSION` for CI only.
* Experiments record the estimator class that was trained, and never substitute another algorithm.
* Ruff: E501 (line length) is advisory; all other rules enforced. Several mid-file imports, unused
  imports and closures were cleaned up.
* `reports/` is tracked; `docker-build.log` is no longer tracked.

### Fixed

* Cross-validation fold count is validated before building the splitter (found by a new test).
* Test isolation no longer leaks CI environment variables into settings.

### Known issues

See `reports/FINAL_PROJECT_AUDIT.md` (open items A-12 to A-18) and `reports/PRODUCTION_READINESS.md`
section 3: admin password rotation pending, no runtime-only database role, no HTTPS yet, no backup
schedule, no frontend component tests, 23 frontend lint warnings.

## 0.5.1 and earlier

Patch 0.5.1 fixed the registration dialog and the Vite dev proxy. Releases `0.5.0-p21` (production)
and `0.5.0-p22` (hardening) are described in `PHASE22_IMPLEMENTATION_REPORT.md` and
`PHASE22_PRODUCTION_HARDENING_REPORT.md`.
