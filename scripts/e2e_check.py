"""End-to-end check of a running stack through its public entry point.

Exercises every major feature with real HTTP calls: auth, RBAC, ownership, datasets, training,
prediction, batch jobs through the worker, experiments/AutoML, SHAP/LIME, drift, monitoring and
user management.

It creates users and data, so only point it at a DISPOSABLE deployment. The API can never create a
superadmin, so create one on that deployment first with scripts/create_superadmin.py and pass its
credentials through the environment (never on the command line):

    $env:E2E_SUPERADMIN_EMAIL = "e2e-root@example.com"
    $env:E2E_SUPERADMIN_PASSWORD = "<the password you gave the bootstrap>"
    python scripts/e2e_check.py --base-url http://127.0.0.1:18080 --confirm-disposable

Exit code 0 only if every check passed. No credentials are printed.
"""

import argparse
import csv
import io
import os
import random
import secrets
import sys
import time

import httpx

API = "/api/v1"


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passed = 0

    def check(self, name: str, ok: bool, detail: object = "") -> bool:
        if ok:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failures.append(name)
            print(f"  FAIL  {name}: {str(detail)[:300]}")
        return ok


def make_csv(rows: int = 150) -> bytes:
    rng = random.Random(7)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["age", "income", "plan", "churned"])
    for _ in range(rows):
        age = rng.randint(18, 80)
        income = round(rng.gauss(50_000, 15_000), 2)
        plan = rng.choice(["basic", "plus", "pro"])
        churned = "yes" if age + rng.gauss(0, 15) > 50 else "no"
        writer.writerow([age, income, plan, churned])
    return buffer.getvalue().encode()


RECORD = {"age": 42, "income": 52000.0, "plan": "plus"}


def wait_for_job(client: httpx.Client, job_id: str, headers: dict, timeout: float = 180) -> dict:
    deadline = time.monotonic() + timeout
    job: dict = {}
    while time.monotonic() < deadline:
        job = client.get(f"{API}/jobs/{job_id}", headers=headers).json()
        if job.get("status") in ("completed", "failed", "cancelled"):
            return job
        time.sleep(1.5)
    return job


def run(base_url: str) -> Checker:
    c = Checker()
    client = httpx.Client(base_url=base_url, timeout=300)
    password = f"E2e{secrets.token_hex(12)}"
    suffix = secrets.token_hex(4)
    mle_email, other_email, viewer_email = (
        f"{name}-{suffix}@example.com" for name in ("owner", "other", "reader")
    )
    root_email = os.environ.get("E2E_SUPERADMIN_EMAIL", "")
    root_password = os.environ.get("E2E_SUPERADMIN_PASSWORD", "")
    if not root_email or not root_password:
        c.check("E2E_SUPERADMIN_EMAIL and E2E_SUPERADMIN_PASSWORD are set", False, "see the script docstring")
        return c

    print("Entry point and health")
    c.check("SPA served", "<div id=\"root\"" in client.get("/").text)
    spa_headers = client.get("/").headers
    c.check("CSP header on SPA", "content-security-policy" in spa_headers)
    health = client.get(f"{API}/health")
    c.check("readiness ok", health.status_code == 200 and health.json()["status"] == "ok", health.text)
    c.check("/metrics not public", "aiml_" not in client.get("/metrics").text)
    c.check("docs disabled by default", client.get("/docs").status_code == 404)

    print("Unauthenticated access")
    for path in ("/datasets", "/models", "/deployments", "/drift/overview", "/jobs", "/experiments"):
        c.check(f"{path} requires auth", client.get(f"{API}{path}").status_code == 401)

    print("Accounts and RBAC")
    public = client.post(f"{API}/auth/register", json={"email": f"public-{suffix}@example.com", "password": password})
    c.check("public registration creates a read-only user", public.status_code == 201 and public.json().get("role") == "user", public.text)
    for role in ("admin", "superadmin"):
        escalate = client.post(
            f"{API}/auth/register",
            json={"email": f"esc-{role}-{suffix}@example.com", "password": password, "role": role},
        )
        c.check(f"registration with role={role} is refused", escalate.status_code == 422, escalate.text)

    login = client.post(f"{API}/auth/login", json={"email": root_email, "password": root_password})
    if not c.check("superadmin login", login.status_code == 200, login.text):
        return c
    tokens = login.json()
    c.check("account is a superadmin", tokens["user"]["role"] == "superadmin", str(tokens["user"].get("role")))
    admin = {"Authorization": f"Bearer {tokens['access_token']}"}  # the superadmin
    c.check("superadmin sees user and audit permissions", {"users:manage", "audit:read"} <= set(tokens["user"]["permissions"]))

    def make_user(email: str, role: str) -> dict:
        response = client.post(
            f"{API}/auth/users",
            json={"email": email, "password": password, "role": role},
            headers=admin,
        )
        c.check(f"superadmin creates {role}", response.status_code == 201, response.text)
        session = client.post(f"{API}/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {session.json()['access_token']}"}

    mle = make_user(mle_email, "admin")  # owns the resources created below
    other = make_user(other_email, "user")  # a different, non-privileged account
    viewer = make_user(viewer_email, "user")
    c.check("admin cannot list users", client.get(f"{API}/auth/users", headers=mle).status_code == 403)
    c.check("admin cannot read the audit log", client.get(f"{API}/audit-logs", headers=mle).status_code == 403)
    c.check("superadmin reads the audit log", client.get(f"{API}/audit-logs", headers=admin).status_code == 200)

    rotated = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    c.check("refresh rotates", rotated.status_code == 200, rotated.text)
    replay = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    c.check("replayed refresh token rejected", replay.status_code == 401)
    users = client.get(f"{API}/auth/users", headers=admin)
    c.check("superadmin lists users", users.status_code == 200 and users.json()["total"] >= 4, users.text)
    c.check("user cannot list users", client.get(f"{API}/auth/users", headers=viewer).status_code == 403)

    print("Datasets")
    files = {"file": ("customers.csv", make_csv(), "text/csv")}
    validated = client.post(f"{API}/datasets/validate", files=files, headers=mle)
    c.check("validate upload", validated.status_code == 200, validated.text)
    c.check("user cannot upload", client.post(f"{API}/datasets", files=files, headers=viewer).status_code == 403)
    bad = client.post(f"{API}/datasets", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=mle)
    c.check("wrong file type rejected", bad.status_code == 415, bad.text)
    uploaded = client.post(f"{API}/datasets", files=files, data={"name": f"customers-{suffix}"}, headers=mle)
    if not c.check("upload dataset", uploaded.status_code == 201, uploaded.text):
        return c
    dataset_id = uploaded.json()["dataset"]["id"]
    c.check("dataset summary", client.get(f"{API}/datasets/{dataset_id}/summary", headers=mle).status_code == 200)
    c.check("other user cannot read dataset", client.get(f"{API}/datasets/{dataset_id}", headers=other).status_code == 403)

    print("Training and prediction")
    train_body = {"dataset_id": dataset_id, "target_column": "churned", "algorithm": "random_forest", "name": f"m-{suffix}"}
    trained = client.post(f"{API}/models/train", json=train_body, headers=mle)
    if not c.check("train model", trained.status_code == 201, trained.text):
        return c
    model_id = trained.json()["id"]
    c.check("list models", client.get(f"{API}/models", headers=mle).json()["total"] >= 1)
    predicted = client.post(f"{API}/models/{model_id}/predict", json={"records": [RECORD, RECORD]}, headers=mle)
    c.check("predict", predicted.status_code == 200 and len(predicted.json()["predictions"]) == 2, predicted.text)
    c.check("other user cannot predict", client.post(f"{API}/models/{model_id}/predict", json={"records": [RECORD]}, headers=other).status_code == 403)
    history = client.get(f"{API}/predictions/history", headers=mle)
    c.check("prediction history", history.status_code == 200 and history.json()["total"] >= 1, history.text)
    log_id = history.json()["items"][0]["id"]
    truth = client.post(f"{API}/predictions/history/{log_id}/ground-truth", json={"ground_truth": ["yes", "no"]}, headers=mle)
    c.check("submit ground truth", truth.status_code == 200, truth.text)

    print("Background jobs (through the worker)")
    job = client.post(
        f"{API}/jobs",
        json={"job_type": "batch_prediction", "model_id": model_id, "input_config": {"records": [RECORD] * 50}},
        headers=mle,
    )
    if c.check("submit batch job", job.status_code == 201, job.text):
        finished = wait_for_job(client, job.json()["id"], mle)
        c.check("batch job completed", finished.get("status") == "completed", finished)
        c.check("batch job result", len((finished.get("result") or {}).get("predictions", [])) == 50, finished)
    empty = client.post(f"{API}/jobs", json={"job_type": "batch_prediction", "input_config": {}}, headers=mle)
    if c.check("submit job without model", empty.status_code == 201, empty.text):
        finished = wait_for_job(client, empty.json()["id"], mle)
        c.check("job without model fails (no fake success)", finished.get("status") == "failed", finished)
    train_job = client.post(
        f"{API}/jobs",
        json={"job_type": "model_training", "input_config": {**train_body, "name": f"job-{suffix}", "algorithm": "linear"}},
        headers=mle,
    )
    if c.check("submit training job", train_job.status_code == 201, train_job.text):
        finished = wait_for_job(client, train_job.json()["id"], mle)
        c.check("training job completed", finished.get("status") == "completed", finished)
    c.check("job metrics", client.get(f"{API}/jobs/metrics", headers=mle).status_code == 200)

    print("Experiments / AutoML")
    experiment = client.post(
        f"{API}/experiments",
        json={
            "name": f"exp-{suffix}",
            "dataset_id": dataset_id,
            "target_column": "churned",
            "problem_type": "classification",
            "algorithm": "random_forest",
            "search_strategy": "grid",
            "hyperparameter_config": {"n_estimators": [10, 20]},
            "cv_folds": 2,
        },
        headers=mle,
    )
    if c.check("create experiment", experiment.status_code == 201, experiment.text):
        experiment_id = experiment.json()["id"]
        run_result = client.post(f"{API}/experiments/{experiment_id}/run", headers=mle)
        ok = run_result.status_code == 200 and run_result.json()["status"] == "completed"
        c.check("run experiment", ok, run_result.text)
        if ok:
            registered = run_result.json()["registered_model_id"]
            used = client.post(f"{API}/models/{registered}/predict", json={"records": [RECORD]}, headers=mle)
            c.check("experiment model predicts", used.status_code == 200, used.text)
        compared = client.get(f"{API}/experiments/compare", params={"experiment_ids": experiment_id}, headers=mle)
        c.check("compare experiments", compared.status_code == 200, compared.text)
        c.check("other user cannot read experiment", client.get(f"{API}/experiments/{experiment_id}", headers=other).status_code == 403)

    print("Explainability")
    base = f"{API}/models/{model_id}/explainability"
    c.check("explainability summary", client.get(f"{base}/summary", headers=mle).status_code == 200)
    importance = client.get(f"{base}/feature-importance", headers=mle)
    c.check("global importance uses SHAP", importance.status_code == 200 and importance.json()["method"] == "shap_kernel", importance.text)
    shap = client.post(f"{base}/shap", json={"record": RECORD}, headers=mle)
    c.check("local SHAP", shap.status_code == 200 and shap.json()["feature_contributions"], shap.text)
    lime = client.post(f"{base}/lime", json={"record": RECORD}, headers=mle)
    c.check("local LIME", lime.status_code == 200 and lime.json()["rule_contributions"], lime.text)

    print("Deployment, monitoring and drift")
    deployed = client.post(f"{API}/models/{model_id}/deploy", json={}, headers=admin)
    c.check("deploy model", deployed.status_code == 200, deployed.text)
    c.check("list deployments", client.get(f"{API}/deployments", headers=mle).json()["total"] >= 1)
    c.check("deployments scoped", client.get(f"{API}/deployments", headers=other).json()["total"] == 0)
    c.check("monitoring overview", client.get(f"{API}/monitoring/overview", headers=mle).status_code == 200)
    c.check("model monitoring", client.get(f"{API}/monitoring/models/{model_id}", headers=mle).status_code == 200)
    for _ in range(3):
        client.post(f"{API}/models/{model_id}/predict", json={"records": [RECORD] * 5}, headers=mle)
    quality = client.post(f"{API}/drift/models/{model_id}/analyze-quality", headers=mle)
    c.check("data quality report", quality.status_code == 200, quality.text)
    drift = client.post(f"{API}/drift/models/{model_id}/analyze-drift", json={}, headers=mle)
    c.check("feature drift report", drift.status_code == 200, drift.text)
    performance = client.post(f"{API}/drift/models/{model_id}/analyze-performance", headers=mle)
    c.check("performance report", performance.status_code == 200, performance.text)
    c.check("drift overview", client.get(f"{API}/drift/overview", headers=mle).status_code == 200)
    c.check("drift reports", client.get(f"{API}/drift/models/{model_id}/reports", headers=mle).json()["total"] >= 3)
    c.check("undeploy model", client.post(f"{API}/models/{model_id}/undeploy", headers=admin).status_code == 200)
    c.check("AI status", client.get(f"{API}/ai/status", headers=mle).status_code == 200)
    return c


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--confirm-disposable", action="store_true")
    args = parser.parse_args()
    if not args.confirm_disposable:
        print("Refusing to run: this creates users and data. Pass --confirm-disposable.")
        return 2
    result = run(args.base_url.rstrip("/"))
    print(f"\n{result.passed} passed, {len(result.failures)} failed")
    for name in result.failures:
        print(f"  FAILED: {name}")
    return 1 if result.failures else 0


if __name__ == "__main__":
    sys.exit(main())
