# Screenshot Checklist

No screenshots are included in the repository: they must be taken from a running copy of the
application so they show real behaviour. Use a local copy with disposable data (never production).
Blur or avoid showing email addresses of real people. Tick each item when captured.

Save images in `docs/college-submission/screenshots/` (create the folder) using the file names
below, and refer to them from the report.

| # | File name | Screen | What must be visible |
|---|---|---|---|
| 1 | `01-login.png` | Sign-in / create-account dialog | The registration form has **no role field** and says new accounts have User access |
| 2 | `02-dashboard-superadmin.png` | Landing page as superadmin | Sidebar with User Administration, Audit Logs, System Settings, My Profile |
| 3 | `03-dashboard-user.png` | Same page as a plain user | Sidebar **without** the administration pages and without upload/train controls |
| 4 | `04-user-administration.png` | User Administration | Account list, role selector (User/Admin only), grant/revoke superadmin |
| 5 | `05-dataset-upload.png` | Dataset Management | Upload card and the validation report |
| 6 | `06-dataset-preview.png` | Dataset detail → Data Preview | First rows, missing values shown as a dash |
| 7 | `07-dataset-profile.png` | Dataset detail → Statistical Profile | Missing values, duplicates, column statistics |
| 8 | `08-training.png` | Training Studio | Dataset, target, algorithm choice (four options) and a finished run |
| 9 | `09-job-status.png` | Job management | A completed training job with progress/status |
| 10 | `10-model-metrics.png` | Model detail | Train/validation/test metrics, baseline, **cross-validation** block, confusion matrix |
| 11 | `11-prediction-single.png` | Predictions | Single prediction with probabilities |
| 12 | `12-prediction-batch.png` | Predictions | Batch prediction results |
| 13 | `13-shap-global.png` | Explainability Studio | Global feature importance |
| 14 | `14-shap-lime-local.png` | Explainability Studio | A local SHAP and a local LIME explanation |
| 15 | `15-deployment.png` | Deployment Monitoring | Deployed model and readiness checklist |
| 16 | `16-drift.png` | Data Drift Monitoring | A drift or data-quality report and alerts |
| 17 | `17-audit-log.png` | Audit Logs (superadmin) | Role change / deactivation / deployment entries |
| 18 | `18-forbidden.png` | Browser dev tools network tab as a plain user | A `403` response to an admin-only call |
| 19 | `19-profile.png` | My Profile | Display name form and change-password form |
| 20 | `20-docker-ps.png` | Terminal: `docker compose ps` | db, app, worker, frontend all healthy |
| 21 | `21-tests.png` | Terminal: the test commands | The pass counts from `reports/FINAL_TEST_REPORT.md` |
| 22 | `22-ci.png` | GitHub Actions run | All jobs green (only after they actually are) |
| 23 | `23-er-diagram.png` | Rendered `diagrams/er-diagram.mmd` | Render with any Mermaid viewer (e.g. the GitHub preview) |
| 24 | `24-architecture.png` | Rendered `diagrams/architecture.mmd` | |
