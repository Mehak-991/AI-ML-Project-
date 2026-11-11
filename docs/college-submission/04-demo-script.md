# Demonstration Script (about 12 minutes)

Run the demo on your own copy, never on production data. Start it with
[the local run guide](../LOCAL_DEVELOPMENT.md) (Docker) and create the first superadmin as described
there. Have two browser profiles ready: one signed in as a superadmin, one as a plain user.

| Time | Step | What to do | What to say / show |
|---|---|---|---|
| 0:00 | Open the app | `http://localhost/` | The React app is served by Nginx, which also proxies `/api`. |
| 0:30 | Register | Use "Create account" | The form has no role field. Every self-registered account is a `user`. |
| 1:00 | Sign in as superadmin | | Navigation shows User Administration, Audit Logs, System Settings. |
| 1:30 | Role-aware UI | Switch to the user profile | The user sees no upload/train/deploy controls and no admin pages. |
| 2:00 | Create an admin | User Administration → create account with role Admin | Only a superadmin can do this; a superadmin cannot be created from the web at all. |
| 3:00 | Upload a dataset | As admin: Dataset Management → upload `datasets/examples/synthetic_classification.csv` | Validation report, missing values, duplicates. |
| 4:00 | Preview and profile | Open the dataset → Data Preview, Statistical Profile | First rows, types, distributions. |
| 5:00 | Train a model | Training Studio → choose the target column and an algorithm | Job runs in the worker; status updates. |
| 6:00 | Evaluate | Model Registry → open the model | Train/validation/test metrics, baseline, cross-validation, confusion matrix. Explain why a baseline is shown. |
| 7:00 | Predict | Predictions → single record, then a batch | Input is validated against the stored feature schema. |
| 8:00 | Explain | Explainability Studio → global importance, one SHAP and one LIME explanation | Say what each shows. |
| 9:00 | Deploy and monitor | Deployment Monitoring → deploy; Drift Monitoring → run quality/drift analysis | Alerts and reports. |
| 10:00 | Access control | As the plain user try the same API through the UI | Forbidden responses; the server enforces it, not the browser. |
| 10:30 | Audit log | As superadmin: Audit Logs | Role change and deployment entries; mention that the database rejects edits and deletes. |
| 11:30 | Profile | My Profile → change the display name; mention password change signs out all sessions | |
| 12:00 | Close | | Tests, Docker, CI, honest limitations. |

## If something goes wrong

* The app does not load: `docker compose ps`; look at `docker compose logs app`.
* Login fails after a restart: tokens expire; sign in again.
* Training seems stuck: check the worker container is healthy (`docker compose ps worker`).
