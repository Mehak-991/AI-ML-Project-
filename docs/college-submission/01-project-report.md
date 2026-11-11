# AIProject — A Role-Based, Explainable Machine Learning Platform

**Final Project Report**

| | |
|---|---|
| Student | *(your name and roll number)* |
| Guide | *(guide's name)* |
| Institution / Department | *(college, department)* |
| Academic year | *(year)* |
| Repository | `Mehak-991/AI-ML-Project-` |

> Everything in this report describes what exists in the repository and was verified. Numbers come
> from [reports/FINAL_TEST_REPORT.md](../../reports/FINAL_TEST_REPORT.md). Placeholders in italics
> are for you to fill in. Diagrams are Mermaid sources in [diagrams/](diagrams/).

---

## 1. Abstract

AIProject is a web platform for supervised machine learning on tabular data. Users upload datasets,
train and compare models, run predictions and obtain SHAP and LIME explanations, deploy models and
monitor them for data drift. Because several people share the same assets, the platform adds what
notebooks lack: three-level role-based access control enforced on the server, rotating authentication
tokens, Argon2id password storage, an append-only audit log, and a containerised deployment with
automated tests. The backend is FastAPI with PostgreSQL; the frontend is React with TypeScript; the
system runs as five Docker Compose services behind Nginx.

## 2. Introduction

Machine-learning work moves from experiment to shared use. At that point questions arise that a
model file cannot answer: who may train, who may only use, who changed a role, can we explain this
prediction, and can we run it somewhere else. AIProject answers them in one application.

## 3. Problem statement

Student and small-team ML projects typically stop at a notebook. Datasets and models sit in folders
with no access control, results are not reproducible, predictions are not explained, nothing records
who did what, and deployment is manual and unsafe.

## 4. Objectives

1. Store datasets with automatic validation and profiling.
2. Train models reproducibly with leakage-safe preprocessing and honest evaluation.
3. Serve single and batch predictions with explanations.
4. Separate responsibilities with three roles enforced by the server.
5. Record privileged actions in a tamper-resistant audit log.
6. Run background work reliably and monitor deployed models for drift.
7. Package everything so it can be started with Docker and verified by automated tests.

## 5. Scope

In scope: tabular classification and regression; CSV and Excel input; four scikit-learn algorithm
families; web UI and REST API; Docker deployment. Out of scope: images/audio, distributed training,
single sign-on, email-based password reset, and a hosted public deployment (configuration is provided
but a domain and certificate are required).

## 6. Existing system

A typical workflow: a Jupyter notebook trains a model, the file is shared by chat or e-mail, anyone
who has it can run it, there is no record of use, and explanations, if any, are ad hoc.

## 7. Proposed system

One governed platform with a registry of datasets and models, a job queue for long work, a
permission model, an audit trail and a repeatable deployment (see sections 12 and 19).

## 8. Functional requirements

| ID | Requirement | Where implemented |
|---|---|---|
| FR1 | Register, log in, refresh, log out; change password; edit own profile | `app/api/routes/auth.py`, `ProfilePage.tsx` |
| FR2 | Registration always yields a normal user | `UserRegisterRequest` (no role field), `register_user` |
| FR3 | Superadmin manages accounts and roles; last superadmin protected | `auth_service.py`, `users.py` repository |
| FR4 | Upload CSV/XLSX, validate, profile, preview | `dataset_service.py`, `app/ml/ingestion.py`, `profiling.py` |
| FR5 | Train a model with a chosen algorithm and target | `app/ml/training.py`, `model_service.py` |
| FR6 | Evaluate with several metrics, baseline and cross-validation | `training.py` |
| FR7 | Version and persist models with integrity checks | `app/ml/persistence.py` |
| FR8 | Single and batch prediction with history | `prediction.py`, `predictions` routes |
| FR9 | SHAP and LIME explanations, feature importance | `explainability_service.py` |
| FR10 | Background jobs (training, batch prediction) with status | `job_service.py`, `scripts/run_worker.py` |
| FR11 | Experiments with hyper-parameter search | `experiment_service.py` |
| FR12 | Deploy/undeploy models; monitor usage | `deployment_service.py` |
| FR13 | Data-quality, drift and performance reports with alerts | `drift_service.py` |
| FR14 | Audit log of privileged operations (superadmin only) | `audit_service.py`, `AuditLogsPage.tsx` |

## 9. Non-functional requirements

| Attribute | Implementation |
|---|---|
| Security | Server-side RBAC (deny by default), Argon2id, JWT with rotating refresh tokens, rate limiting, upload and path hardening, security headers, CSP |
| Reliability | Health checks, restart policies, database-backed job leasing and recovery, graceful shutdown |
| Maintainability | Layered code (routes → services → repositories), type hints, Ruff rules in CI, migrations |
| Reproducibility | Fixed random seeds, stored preprocessing pipeline, dataset checksum, library versions in model metadata |
| Portability | Docker Compose; Python 3.12; PostgreSQL 18 |
| Observability | Structured logs with request IDs, optional Prometheus metrics |
| Testability | Unit, PostgreSQL integration and end-to-end suites; CI pipeline |

## 10. Technology stack

| Layer | Technology |
|---|---|
| Language/runtime | Python 3.12, Node 22 |
| Backend | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Database | PostgreSQL 18 |
| Machine learning | pandas, NumPy, scikit-learn, joblib, SHAP, LIME |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Axios |
| Delivery | Docker, Docker Compose, Nginx |
| Quality | pytest, Ruff (incl. bandit rules), pip-audit, npm audit, oxlint, gitleaks, GitHub Actions |

## 11. System architecture

See [diagrams/architecture.mmd](diagrams/architecture.mmd). The browser talks only to Nginx, which
serves the compiled React application and proxies `/api` to the FastAPI application on an internal
network. The API and the worker share PostgreSQL and the model/upload storage. A one-shot migration
service applies Alembic migrations before the API starts. Request handling passes through
middleware for request IDs, security headers, CORS, rate limiting and body-size limits.

## 12. Module descriptions

| Module | Responsibility |
|---|---|
| `app/core` | Settings, security (hashing, tokens), the permission registry (`permissions.py`), exceptions |
| `app/api` | Dependencies (`deps.py`: authentication, permission checks, deny-by-default policy) and 15 route modules |
| `app/services` | Use cases: auth, datasets, models, experiments, deployments, drift, explainability, jobs, audit, health |
| `app/repositories` | Database queries (e.g. user queries with row locks for the last-superadmin guard) |
| `app/database` | SQLAlchemy models and sessions |
| `app/ml` | Ingestion, validation, profiling, preprocessing, training, persistence, prediction |
| `app/ai` | Optional language-model, embedding and classification helpers (off by default) |
| `scripts` | Server-side tools: superadmin bootstrap, password recovery, backup/restore, worker, health, end-to-end check |
| `frontend/src` | Pages, components, API client, authentication context with permission checks |
| `alembic` | 14 migrations |

## 13. Database design

Twelve tables: `users`, `refresh_tokens`, `datasets`, `ml_models`, `experiments`, `experiment_runs`,
`jobs`, `deployments`, `prediction_logs`, `drift_reports`, `drift_alerts`, `audit_logs`. The entity–
relationship diagram, generated from the SQLAlchemy metadata, is in
[diagrams/er-diagram.mmd](diagrams/er-diagram.mmd) (18 foreign-key relationships).
Notable constraints: a CHECK constraint on the allowed roles; unique e-mail; `audit_logs` has no
foreign keys (it keeps e-mail snapshots so entries survive account deletion) and database triggers
that reject UPDATE, DELETE and TRUNCATE.

## 14. Data-flow diagrams

* Level 0: [diagrams/dfd-level-0.mmd](diagrams/dfd-level-0.mmd) — the system, its three kinds of
  users and the optional external LLM provider.
* Level 1: [diagrams/dfd-level-1.mmd](diagrams/dfd-level-1.mmd) — six processes (authentication and
  RBAC, dataset management, training and evaluation, prediction and explainability, deployment and
  drift monitoring, administration and audit) and six data stores.
* Request and authorisation flow: [diagrams/rbac-and-request-flow.mmd](diagrams/rbac-and-request-flow.mmd).

## 15. API documentation

See [api-reference.md](api-reference.md): all 71 method/path pairs with the permission each one
requires, generated from the running application.

## 16. AI/ML methodology

1. **Ingestion and validation.** CSV or Excel is parsed with pandas; the file type, size, row and
   column counts are checked; the validation report lists errors and warnings (duplicate rows,
   missing values, constant columns, etc.).
2. **Feature selection.** All non-target columns by default, with explicit include/exclude lists;
   unusable columns (for example identifiers) are dropped with a recorded reason.
3. **Splitting.** Train, validation and test splits (default 60/20/20), stratified for
   classification when every class is large enough, with a fixed random seed. Duplicate rows are removed before splitting.
4. **Preprocessing (fitted on training data only).** Numeric: median imputation and standard
   scaling. Categorical: constant imputation and one-hot encoding with a cap on categories and
   handling of unseen values. The fitted transformer is part of the saved pipeline, so prediction
   applies exactly the same steps.
5. **Algorithms.** Linear/logistic regression, random forest, gradient boosting and decision tree,
   for classification and regression.
6. **Evaluation.** Classification: accuracy, balanced accuracy, precision, recall and F1 (macro),
   ROC-AUC, log-loss and the confusion matrix. Regression: MAE, RMSE, median absolute error and R².
   Metrics are stored for train, validation and test, together with a **baseline** (most frequent
   class or the mean) so a model has to beat a trivial predictor.
7. **Cross-validation.** Up to five folds (stratified for classification) on the training and
   validation rows only; mean and standard deviation of accuracy/F1 or R²/RMSE are stored. It is
   skipped, with a reason, if a class is too small or the training set exceeds 20,000 rows.
8. **Persistence.** The pipeline is saved with joblib under a random name; its SHA-256 is stored in
   the database and verified before loading; metadata records library versions and the dataset hash.
9. **Prediction.** Records are validated against the stored feature schema before scoring; each
   prediction is logged.
10. **Explainability.** SHAP (global importance and per-record contributions) and LIME (per-record
    local surrogate).
11. **Monitoring.** Data-quality, feature-drift (PSI, Kolmogorov–Smirnov, chi-square) and
    performance reports compare production inputs with the training reference and raise alerts.

## 17. Authentication and RBAC

* **Tokens.** Short-lived JWT access token; refresh token stored hashed, rotated on every use;
  reuse of an old refresh token is rejected and revokes the sessions; password change and logout
  revoke tokens.
* **Roles and permissions.** Defined once in `app/core/permissions.py`:

| Role | Permissions |
|---|---|
| user | `resources:read`, `predict:run`, `profile:manage` |
| admin | user + `ml:operate`, `deployments:manage` |
| superadmin | admin + `users:read`, `users:manage`, `roles:assign`, `superadmin:grant`, `audit:read`, `settings:read` |

* **Deny by default.** Every route declares its permission; an application-wide dependency refuses
  any route that declares none.
* **No self-elevation.** Registration has no role field; the profile endpoint accepts only a display
  name; only a superadmin changes roles, and only between user and admin; a superadmin is created
  only by a server-side command; the last active superadmin cannot be demoted, deactivated or deleted
  (checked under a database row lock).
* **Audit.** Role changes, deactivation, deletion, superadmin grants and revocations, deployments and
  the server-side commands are written in the same transaction as the change; database triggers make
  the table append-only.
* **The UI is a convenience.** The server returns the caller's computed permissions and the UI hides
  what the API would refuse; the API enforces every rule independently.

## 18. Implementation details

* **Layering** keeps HTTP, business rules and queries apart, so rules such as the last-superadmin guard
  live in one place and are unit-testable.
* **Job queue.** Jobs are rows in PostgreSQL; the worker claims them with `FOR UPDATE SKIP LOCKED`
  and a lease with heartbeats, and a reaper recovers jobs from dead workers.
* **Migrations.** Sequential Alembic scripts; the RBAC migration refuses to guess an unknown legacy
  role and records its mappings in the audit log.
* **Frontend.** One Axios client with token refresh; permission-filtered navigation; pages for
  datasets, training, models, predictions, explainability, deployment, drift, jobs, users, audit,
  settings and the user's own profile.

## 19. Testing methodology

Three levels, plus tool-based checks (results in the test report):

1. **Unit tests** (SQLite test double): permission matrix over every route and role, account rules,
   ML training/persistence/prediction, hardening, migrations.
2. **PostgreSQL integration tests**: real row-lock concurrency, real constraints and triggers,
   migrations against PostgreSQL.
3. **End-to-end on a disposable Docker stack**: a script drives the live API through the whole
   workflow with several accounts, including attacks (role escalation, token replay, cross-user access).
4. **Static and supply-chain checks**: Ruff, pip-audit, npm audit, gitleaks, type-check/build,
   Docker Compose validation.

## 20. Results

| Result | Value (source: test report) |
|---|---|
| Unit tests | 743 passed, 1 skipped, 0 failed |
| PostgreSQL integration tests | 36 passed, 0 failed |
| End-to-end checks | 97 passed, 0 failed |
| Lint / dependency / secret scans | Ruff clean; no known Python or npm vulnerabilities; no secrets in Git history |
| Persistence | After restarting the services, database rows and model/upload files were unchanged |

Model quality figures depend on the dataset you train on; take them from the Model Registry screen of
your own run and cite the dataset. This report deliberately contains no invented accuracy numbers.

## 21. Limitations

* Tabular supervised learning only.
* No email-based password reset and no single sign-on.
* Datasets and models cannot be deleted through the API (by design so far; deletion would need ownership and dependency rules).
* No hosted public deployment or HTTPS yet (needs a domain and certificate).
* The frontend has no component-test suite; it is verified by type-checking, the build, consistency
  tests and the end-to-end run.
* The application connects to the database as its owner (no separate low-privilege runtime role).
* Optional language-model features need external services and were not exercised against real providers.

## 22. Future enhancements

Separate database roles; email-based password reset; Vitest component tests; scheduled automatic
backups; model-card export; additional algorithms (e.g. gradient-boosted libraries) and automated
feature engineering; role-scoped sharing of individual datasets.

## 23. Conclusion

The project delivers a complete, tested platform that connects the machine-learning workflow with
the controls needed to share it: validated data, honest evaluation, explanations, governed access and
an auditable, reproducible deployment.

## 24. Installation and execution guide

Follow [../LOCAL_DEVELOPMENT.md](../LOCAL_DEVELOPMENT.md). In short:

```bash
cp .env.example .env          # set POSTGRES_PASSWORD and JWT_SECRET_KEY
docker compose up -d --build
docker compose run --rm --no-deps -it app python scripts/create_superadmin.py --email you@example.com
# open http://localhost/
```

## 25. References

(Real, standard references for the techniques and standards used.)

1. Breiman, L. (2001). *Random Forests*. Machine Learning, 45(1), 5–32.
2. Friedman, J. H. (2001). *Greedy function approximation: a gradient boosting machine*. Annals of
   Statistics, 29(5), 1189–1232.
3. Lundberg, S. M. & Lee, S.-I. (2017). *A Unified Approach to Interpreting Model Predictions*.
   Advances in Neural Information Processing Systems 30 (SHAP).
4. Ribeiro, M. T., Singh, S. & Guestrin, C. (2016). *"Why Should I Trust You?": Explaining the
   Predictions of Any Classifier*. Proc. ACM SIGKDD (LIME).
5. Pedregosa, F. et al. (2011). *Scikit-learn: Machine Learning in Python*. JMLR 12, 2825–2830.
6. Jones, M., Bradley, J. & Sakimura, N. (2015). *JSON Web Token (JWT)*. RFC 7519.
7. Biryukov, A., Dinu, D., Khovratovich, D. & Josefsson, S. (2021). *Argon2 Memory-Hard Function
   for Password Hashing and Proof-of-Work Applications*. RFC 9106.
8. OWASP Foundation. *OWASP Application Security Verification Standard (ASVS)* and *OWASP Top 10*.
9. FastAPI, SQLAlchemy, Alembic, PostgreSQL, React and Docker official documentation.
