# API Reference

Generated from the running application's route table (every route and the permission it declares).
Base path `/api/v1` unless shown. Interactive documentation (`/docs`) is disabled by default; set
`DOCS_ENABLED=true` on a development copy to browse the OpenAPI schema.

Authentication: `Authorization: Bearer <access token>` from `POST /api/v1/auth/login`
(`{"email", "password"}` → `access_token`, `refresh_token`, `user`). Refresh with
`POST /api/v1/auth/refresh`. Errors always look like
`{"error": {"code": "...", "message": "..."}}`.

Roles: **user** < **admin** < **superadmin**. "Lowest role" is the least-privileged role that holds
the permission (higher roles hold it too). Object-level ownership rules also apply to non-privileged
users.

Permissions: `resources:read`, `predict:run`, `profile:manage` (user); `ml:operate`,
`deployments:manage` (admin); `users:read`, `users:manage`, `roles:assign`, `superadmin:grant`,
`audit:read`, `settings:read` (superadmin).

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
| GET | `/api/v1/datasets/{dataset_id}/preview` | `resources:read` | user |
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


## Notes on selected endpoints

| Endpoint | Behaviour |
|---|---|
| `POST /datasets` | Multipart upload (`file`, optional `name`); CSV/XLSX only; size, row and column limits; returns the dataset and its validation report |
| `GET /datasets/{id}/preview?limit=20` | First rows (1–100), missing values as `null`, with total row count |
| `POST /models/train` | Body: `dataset_id`, `target_column`, optional `algorithm` (`linear`, `random_forest`, `gradient_boosting`, `decision_tree`), `problem_type`, split sizes. Returns the model with metrics (`train`, `validation`, `test`, `baseline_test`) and `training_metadata` (including `cross_validation`) |
| `POST /models/{id}/predict` | Body: `{"records": [ {...} ]}` validated against the model's feature schema |
| `POST /models/{id}/explainability/shap` / `lime` | Local explanations for one record |
| `POST /experiments` then `/experiments/{id}/run` | Grid-search experiment that registers the best model |
| `POST /jobs` | Background job executed by the worker |
| `PATCH /auth/me` | Only `full_name` is accepted; unknown fields (e.g. `role`) are rejected with 422 |
| `POST /auth/change-password` | Needs the current password; revokes all refresh tokens |
| `PATCH /auth/users/{id}` | Superadmin only; `role` may only be `user` or `admin` |
| `DELETE /auth/users/{id}?confirm_email=...` | Superadmin only; refused when the account owns resources or is the last superadmin |
