# Presentation Outline (18 slides)

Each slide lists the content to put on it and what to say. Everything refers to features that exist
in the repository; capture the screenshots yourself from a running copy (see
[06-screenshot-checklist.md](06-screenshot-checklist.md)). Do not add numbers that are not in
[reports/FINAL_TEST_REPORT.md](../../reports/FINAL_TEST_REPORT.md).

| # | Slide | Content | Speaker notes |
|---|---|---|---|
| 1 | Title | AIProject — A Role-Based, Explainable ML Platform; your name, guide, college | One sentence: "a platform where a team can safely train, share and explain machine-learning models". |
| 2 | Problem | Notebooks have no access control, no audit, no deployment | Models are shared informally; nobody knows who changed or used what. |
| 3 | Objectives | Safe sharing, reproducible training, explainable predictions, auditability, easy deployment | Map each objective to a later slide. |
| 4 | Existing vs proposed | Notebook/scripts vs one governed web platform | Keep it to what you built. |
| 5 | Technology stack | FastAPI, PostgreSQL, scikit-learn, SHAP/LIME, React/TypeScript, Docker, Nginx, GitHub Actions | One line on why each was chosen. |
| 6 | Architecture | `diagrams/architecture.mmd` | Browser → Nginx → FastAPI → PostgreSQL, worker for background jobs. |
| 7 | Data flow | `diagrams/dfd-level-0.mmd` and `dfd-level-1.mmd` | Six processes, six data stores. |
| 8 | Database | `diagrams/er-diagram.mmd` (12 tables) | Point out users, refresh_tokens, ml_models, jobs, audit_logs. |
| 9 | Roles and permissions | The three-role table | The server decides; the UI only hides what the API would refuse. |
| 10 | Security design | Argon2id, rotating refresh tokens, deny-by-default routes, audit log that the database itself will not let anyone edit | Show the request flow diagram. |
| 11 | Dataset management | Upload, validation report, preview, profile | Live demo or screenshot. |
| 12 | Training and evaluation | Four algorithms, baseline, train/validation/test, cross-validation, confusion matrix | Explain why accuracy alone is not enough and why a baseline is shown. |
| 13 | Prediction | Single and batch, history | Demo. |
| 14 | Explainability | SHAP global importance, LIME local explanation | Explain in one sentence what each does. |
| 15 | MLOps | Jobs/worker, experiments, deployments, drift alerts | Mention the job queue lives in PostgreSQL. |
| 16 | Testing | Unit, PostgreSQL integration, end-to-end on a disposable stack, security tests | Quote the numbers from the test report only. |
| 17 | Deployment | Docker Compose, health checks, backups, migration plan with a rollback | Be explicit that public HTTPS needs a domain. |
| 18 | Limitations, future work, conclusion | Tabular data only; no SSO; no hosted deployment yet; possible additions | End with what you learned. |
