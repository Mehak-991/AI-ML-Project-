# Viva Questions and Answers

Answers describe what this project actually does. If you are asked about something that is not
implemented, say so plainly (see the limitations section of the report).

## Project and design

**1. What does your project do?**
It is a web platform for tabular machine learning. People upload datasets, train and compare
models, ask for predictions with SHAP/LIME explanations, deploy and monitor models, and an
administrator manages accounts. Access is controlled by three roles and every privileged action is
audited.

**2. Why FastAPI?**
It gives type-checked request/response models (Pydantic), automatic OpenAPI documentation and
dependency injection, which the project uses for authentication and permissions.

**3. Why PostgreSQL, and why is the job queue inside it?**
PostgreSQL stores everything relational (users, models, audit). The job queue uses row locks
(`SELECT ... FOR UPDATE SKIP LOCKED`-style claiming and leases) so no extra broker such as Redis is
needed; the worker and API share one database and jobs survive restarts.

**4. Describe the architecture.**
Browser → Nginx (serves the React build, adds security headers, proxies `/api`) → FastAPI (routes →
services → repositories → SQLAlchemy) → PostgreSQL; a worker container runs background jobs; model
files and uploads live on persistent volumes. See `diagrams/architecture.mmd`.

**5. What is Alembic?**
A migration tool. Every schema change is a numbered script (0001–0014), so a database can be built
or upgraded reproducibly.

## Machine learning

**6. Which algorithms are supported?**
Linear/logistic regression, random forest, gradient boosting and decision tree, for both
classification and regression, through one scikit-learn pipeline.

**7. How do you avoid data leakage?**
The split happens before preprocessing is fitted; imputers, encoders and scalers are fitted on the
training part only and stored inside the pipeline. Cross-validation uses only the training and
validation rows; the test set is never used for tuning.

**8. Why show a baseline model?**
A model is only useful if it beats a trivial predictor (most frequent class or the mean). The
baseline test score is stored next to the model's score.

**9. Why not report accuracy alone?**
With imbalanced classes accuracy can look good while the model is useless. The project also stores
balanced accuracy, precision, recall, F1, ROC-AUC, log-loss and the confusion matrix (classification)
and MAE, RMSE, median absolute error and R² (regression).

**10. What is cross-validation here?**
The training+validation rows are split into up to five folds; the model is fitted on four and
scored on one, five times. The mean and standard deviation show how stable the score is. It is
skipped (and says why) for very large training sets or when a class has too few rows.

**11. SHAP versus LIME?**
SHAP assigns each feature a contribution based on Shapley values from game theory and can be
aggregated for a global view. LIME fits a small interpretable model around one prediction to explain
that single case. SHAP is used for global importance and local explanations; LIME gives a second,
independent local view.

**12. How are models stored safely?**
Saved with joblib under a random file name; the SHA-256 of the file is stored in the database and
checked before loading, and the loader refuses names that are not plain artifact names (no path
traversal). Loading unpickled files is a risk, so the checksum guards against tampering.

## Security

**13. Explain the roles.**
`user`: read resources, run predictions/explanations, manage own profile. `admin`: also upload,
train, run jobs, monitor drift, deploy. `superadmin`: also manage users and roles, read the audit log
and settings.

**14. How do you stop privilege escalation?**
Registration has no role field (extra fields are rejected). Users cannot change their own role (the
profile endpoint only accepts a display name). Only a superadmin can change roles, and only between
`user` and `admin`; creating a superadmin is only possible with a server-side command. The last
active superadmin can never be removed, demoted or deactivated (checked under a database row lock so
two simultaneous requests cannot both succeed).

**15. What does "deny by default" mean?**
Every route must declare the permission it needs. A route that declares nothing is refused with 403
for everyone, so forgetting to protect a new endpoint fails safely. A test checks every route.

**16. How are passwords stored?**
Argon2id (memory-hard). Older PBKDF2/bcrypt hashes still verify and can be upgraded at the next
login.

**17. What are refresh-token rotation and replay protection?**
Each refresh issues a new refresh token and revokes the old one. Presenting an already-used token is
rejected. Changing the password or logging out revokes tokens.

**18. Why can the audit log not be edited?**
Besides the application never updating it, PostgreSQL triggers reject UPDATE, DELETE and TRUNCATE on
the table.

**19. How is file upload hardened?**
Allowed extensions only, size and row/column limits, content parsed by pandas rather than executed,
stored under a generated name inside the upload directory, and path-escape attempts are refused.

**20. Is HTTPS enabled?**
The configuration for TLS exists (`compose.tls.yaml`, `TLS_DEPLOYMENT.md`) but a real certificate
needs a domain, so it has not been deployed. I do not claim public HTTPS is live.

## Testing and deployment

**21. How did you test it?**
Unit tests, PostgreSQL integration tests (including concurrency tests), migration tests with
upgrade/downgrade, and an end-to-end script that drives a running Docker stack through registration,
upload, training, prediction, explanations, deployment, drift, access-control and audit checks. Exact
counts are in `reports/FINAL_TEST_REPORT.md`.

**22. What is the difference between the user's role in the token and in the database?**
The token only identifies the account. The role is read from the database on every request, so a
demotion or deactivation takes effect immediately and a forged role claim is ignored (tested).

**23. How do you deploy safely?**
Take a verified backup, stop the app, run the migration, create the superadmin with the
server-side command, start the new version, verify, and keep the backup as the rollback. The
step-by-step plan is in `reports/DEPLOYMENT_REPORT.md`.

**24. Why is a database downgrade not used as a rollback?**
The RBAC migration changes the meaning of roles, so a downgrade cannot restore the exact previous
state. Restoring the pre-migration backup into a separate database is the safe rollback.

**25. What are the limitations?**
Tabular data only; no single sign-on or password-reset email; no hosted public deployment yet;
optional language-model features need external services; the frontend has no component-level test
suite (it is covered by type-checking, build, static consistency tests and the end-to-end run).
