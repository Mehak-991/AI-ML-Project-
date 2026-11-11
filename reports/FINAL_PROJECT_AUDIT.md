# Final Project Audit

**Repository:** `Mehak-991/AI-ML-Project-` · **Audited commit:** `main` @ `76012ee` (merge of PR #1),
then fixed on branch `chore/final-completion`. **Read-only on production.** The context given in the
brief was treated as a starting point; each statement was checked (results in section 1).

## 1. Verification of the starting assumptions

| Assumption in the brief | Finding |
|---|---|
| RBAC v2 merged into `main`, latest `76012ee` | ✅ confirmed (PR #1 merged; `origin/main` = `76012ee`) |
| Migration `0014` adds RBAC v2 roles and audit logging | ✅ `alembic/versions/20261111_0014_rbac_v2_roles_and_audit.py` |
| Production database still on `0013` | ✅ read-only check: revision `0013` |
| Candidate images exist, not deployed | ✅ `0.6.0-rc1` existed; `0.6.0-rc2` was built in this phase (disposable use only); production runs `0.5.0-p21` images |
| Backups exist | ✅ `backups/pre-rbac-v2/aiproject_pre_rbac.dump` (+ `volumes/`), older dumps; all Git-ignored |
| RBAC v2 has unit, integration and full-stack tests | ✅ see `FINAL_TEST_REPORT.md` |

## 2. System inventory (from the code)

* **Backend:** `app/` — 15 route modules, 12 service modules, repositories, 12 database tables,
  `app/ml` (ingestion, validation, profiling, preprocessing, training, persistence, prediction,
  visualization), `app/ai` (optional LLM/embedding/classification), worker loop in
  `app/services/job_service.py` run by `scripts/run_worker.py`.
* **API:** 71 method/path pairs (68 under `/api/v1`), each with a declared policy
  (`docs/college-submission/api-reference.md`).
* **Database:** 14 sequential migrations (`0001`–`0014`).
* **Frontend:** React 19 + TypeScript + Vite; 12 pages, 17 components, one API client; navigation is
  permission-driven.
* **Infrastructure:** Compose with db, migration, app, worker, frontend; Nginx with security headers;
  optional TLS and Prometheus overlays; CI workflow with backend, frontend, secret-scan and Docker jobs.

## 3. Findings

Severity: **H**igh, **M**edium, **L**ow, **I**nfo. Status: Fixed / Open / Accepted.

| ID | Sev | Area | Finding and evidence | Files | Status |
|---|---|---|---|---|---|
| A-01 | M | Repo | `reports/` was listed in `.gitignore`, so the required reports could not be committed | `.gitignore` | Fixed |
| A-02 | L | Repo | `docker-build.log` (UTF-16 PowerShell transcript) was tracked; no secrets inside | `docker-build.log` | Fixed (untracked, ignored; remains in old history) |
| A-03 | M | CI | CI linted only a narrow subset (`E9,F63,F7,F82,S`); the project's own config reported 547 findings (381 line-length, 38 import order, 31 unused imports, pyupgrade items, 14 mid-file imports, closures, `== True`) | `pyproject.toml`, `.github/workflows/ci.yml` | Fixed — all fixed or justified; CI now runs the full config |
| A-04 | L | Backend | `app/api/deps.py` had imports mid-file (E402) | `app/api/deps.py` | Fixed |
| A-05 | L | Backend | Loop-variable closures (B023) in drift and explainability code were safe today (called immediately) but fragile | `app/services/drift_service.py`, `explainability_service.py` | Fixed (explicit binding) |
| A-06 | M | ML | Only two algorithms (linear, random forest) and no cross-validation, against the requirement for supported algorithms and CV | `app/ml/training.py`, schemas | Fixed (gradient boosting, decision tree, 5-fold CV, tests) |
| A-07 | M | ML | `experiment_service` mapped *any* algorithm other than `linear` to a random forest and recorded no estimator, so adding algorithms would have silently trained the wrong model | `app/services/experiment_service.py` | Fixed (explicit estimator, `estimator` stored, tests assert it) |
| A-08 | M | ML | A latent bug in the new CV helper (fold count checked after the splitter was built) was caught by a new test before release | `app/ml/training.py` | Fixed |
| A-09 | M | Feature gap | No dataset **row preview** (only statistics) | datasets route/service, UI | Fixed (`GET /datasets/{id}/preview`, UI tab, tests) |
| A-10 | M | Feature gap | API had profile update and change-password endpoints but the UI had **no profile page** | `ProfilePage.tsx`, `api.ts` | Fixed |
| A-11 | M | CI | Tests leaked CI's job-level environment variables; integration tests assumed a migrated schema | `tests/conftest.py`, workflow | Fixed (PR #1) |
| A-12 | I | Auth | Password reset exists only as an operator CLI; no email-based flow | `scripts/reset_password.py` | Accepted (needs an email service / product decision) |
| A-13 | L | Frontend | No component test runner; 23 oxlint warnings (React effect patterns) | `frontend/` | Open — recommend Vitest + Testing Library |
| A-14 | M | Security | No reduced-privilege runtime database role | `compose.yaml` | Open (S-03) |
| A-15 | H | Security | Admin password exposure via committed backups; rotation not confirmed | `GIT_HISTORY_CLEANUP.md` | Open (S-01), owner action |
| A-16 | H | Release | Production still on p21 / revision 0013; p21 cannot read RBAC v2 roles or Argon2id | — | Open (rollout plan, approval gates) |
| A-17 | I | Ops | Production `app`/`worker` were restarted at 11:36:42Z by an unknown actor (not by this work) | — | Open — please check |
| A-18 | L | Ops | No backup schedule; CPU/memory limits not set | `compose.yaml` | Open |
| A-19 | I | Docs | Several historical reports (`FINAL_AUDIT_REPORT.md`, `DOCKER_VERIFICATION_REPORT.md`, …) predate the current state | repo root | Accepted; README labels them historical |
| A-20 | I | API | `/` , `/health` , `/metrics` are public by design (metrics are token-protected and blocked at the edge) | `root.py`, `health.py` | Accepted |

## 4. Areas reviewed with no defect found

Registration defaults and role handling, refresh-token rotation and revocation, audit-log
immutability, last-superadmin protection under concurrency, upload validation and path safety,
model-artifact integrity checks, CORS behaviour, security headers, container hardening, frontend–
backend path consistency (every frontend API path matches a backend route; eight backend routes have
no UI by design: embeddings, token counting, NLP/LLM helpers, `validate`, per-model prediction
history, and change-password which now has the profile page), dependency vulnerabilities, secret
scanning. Details in `SECURITY_AUDIT.md` and `FINAL_TEST_REPORT.md`.

## 5. Not covered

Load/performance beyond earlier phases; real external LLM providers; browser-driven UI testing;
public HTTPS; hosted CI result of the latest commits.
