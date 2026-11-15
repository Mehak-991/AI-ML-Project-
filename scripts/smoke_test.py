"""End-to-end smoke test against a RUNNING server (local, Docker or deployed).

Usage:
    SMOKE_EMAIL=admin@example.com SMOKE_PASSWORD=...         python scripts/smoke_test.py [http://127.0.0.1:8000] [--with-llm] [--cleanup]

The account must be an admin or super_admin (the API is authenticated and role-checked).
Steps: health -> readiness -> database health -> login -> permissions -> AI status ->
token count -> (if the DB is up) upload synthetic CSV -> train -> model metadata ->
predict -> employee create/read/update (+ delete with --cleanup, super_admin only) ->
(if local NLP extras are installed) embeddings -> (with --with-llm) one short chat
completion on the local Ollama model (free, but slow on CPU). Uses only the standard
library. Exit code 1 if any step FAILs. Passwords are read from the environment, never
from the command line, and never printed.
"""

import os

import argparse
import csv
import io
import json
import random
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any

results: list[tuple[str, str, str]] = []


TOKEN: dict[str, str] = {}


def request(
    method: str, url: str, body: Any = None, *, files: dict | None = None, timeout: float = 120
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    if "access" in TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN['access']}"
    data = None
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for field, (filename, content) in files.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
                f'filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n'.encode()
                + content
                + b"\r\n"
            )
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"null")
        except json.JSONDecodeError:
            return exc.code, None


def record(step: str, status: str, detail: str = "") -> None:
    results.append((step, status, detail))
    print(f"{status:<5} {step:<28} {detail}", flush=True)


def synthetic_csv(rows: int = 150) -> bytes:
    rng = random.Random(7)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["num_a", "num_b", "cat_a", "label"])
    for _ in range(rows):
        a, b, c = rng.gauss(50, 10), rng.random(), rng.choice(["red", "green", "blue"])
        score = 0.08 * (a - 50) + 3 * (b - 0.5) + {"red": 1, "green": 0, "blue": -1}[c]
        writer.writerow([round(a, 2), round(b, 4), c, "yes" if score > 0 else "no"])
    return buffer.getvalue().encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--with-llm", action="store_true", help="make one real chat call to the local Ollama model"
    )
    parser.add_argument(
        "--cleanup", action="store_true", help="delete the smoke-test employee (super_admin)"
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"

    status, body = request("GET", f"{base}/health")
    record("liveness", "PASS" if status == 200 else "FAIL", f"HTTP {status}")
    if status != 200:
        return 1

    status, body = request("GET", f"{api}/health")
    components = (body or {}).get("components", {})
    db_state = components.get("database")
    record(
        "readiness",
        "PASS" if status in (200, 503) else "FAIL",
        f"database={db_state} llm={components.get('llm')}",
    )
    status, body = request("GET", f"{api}/health/database")
    record("database health", "PASS" if status in (200, 503) else "FAIL",
           f"status={(body or {}).get('status')} latency_ms={(body or {}).get('latency_ms')}")

    email, password = os.environ.get("SMOKE_EMAIL"), os.environ.get("SMOKE_PASSWORD")
    if not (email and password):
        record("login", "FAIL", "set SMOKE_EMAIL and SMOKE_PASSWORD (admin or super_admin)")
        return 1
    status, body = request("POST", f"{api}/auth/login", {"email": email, "password": password})
    if status != 200:
        record("login", "FAIL", f"HTTP {status}")
        return 1
    TOKEN["access"] = body["access_token"]
    role = body["user"]["role"]
    record("login", "PASS", f"role={role}")
    status, body = request("GET", f"{api}/auth/me/permissions")
    record("permissions", "PASS" if status == 200 else "FAIL",
           f"{len((body or {}).get('permissions', []))} permissions")

    status, ai = request("GET", f"{api}/ai/status")
    record("ai status", "PASS" if status == 200 else "FAIL", f"HTTP {status}")
    ai = ai or {}

    status, body = request("POST", f"{api}/tokens/count", {"text": "Hello smoke test"})
    record(
        "token count",
        "PASS" if status == 200 and body["tokens"] > 0 else "FAIL",
        f"{(body or {}).get('tokens')} tokens, approximate={(body or {}).get('approximate')}",
    )

    if db_state == "ok":
        status, body = request(
            "POST", f"{api}/datasets", files={"file": ("smoke.csv", synthetic_csv())}
        )
        ok = status == 201
        record("dataset upload", "PASS" if ok else "FAIL", f"HTTP {status}")
        if ok:
            dataset_id = body["dataset"]["id"]
            status, model = request(
                "POST",
                f"{api}/models/train",
                {"dataset_id": dataset_id, "target_column": "label", "name": "smoke-test"},
            )
            ok = status == 201
            accuracy = (model or {}).get("metrics", {}).get("test", {}).get("accuracy")
            detail = f"HTTP {status} version={(model or {}).get('version')} accuracy={accuracy}"
            record("train", "PASS" if ok else "FAIL", detail)
            if ok:
                status, _ = request("GET", f"{api}/models/{model['id']}")
                record("model metadata", "PASS" if status == 200 else "FAIL", f"HTTP {status}")
                status, body = request(
                    "POST",
                    f"{api}/models/{model['id']}/predict",
                    {"records": [{"num_a": 60, "num_b": 0.9, "cat_a": "red"}]},
                )
                record(
                    "predict",
                    "PASS" if status == 200 else "FAIL",
                    f"HTTP {status} {(body or {}).get('predictions')}",
                )
    else:
        record("dataset/train/predict", "SKIP", "database not ready")

    if db_state == "ok":
        code = f"SMOKE-{uuid.uuid4().hex[:8].upper()}"
        status, emp = request("POST", f"{api}/employees", {
            "employee_code": code, "first_name": "Smoke", "last_name": "Test",
            "email": f"{code.lower()}@example.com", "department": "QA",
            "job_title": "Smoke tester", "hire_date": "2025-01-01", "salary": "1000.00",
        })
        record("employee create", "PASS" if status == 201 else "FAIL", f"HTTP {status}")
        if status == 201:
            status, _ = request("PATCH", f"{api}/employees/{emp['id']}", {"job_title": "Updated"})
            record("employee update", "PASS" if status == 200 else "FAIL", f"HTTP {status}")
            status, body = request("GET", f"{api}/employees", None)
            record("employee list", "PASS" if status == 200 else "FAIL",
                   f"total={(body or {}).get('total')}")
            if args.cleanup:
                status, _ = request("DELETE", f"{api}/employees/{emp['id']}")
                expected = 204 if role == "super_admin" else 403
                record("employee delete", "PASS" if status == expected else "FAIL",
                       f"HTTP {status} (role={role})")
        status, body = request("GET", f"{api}/audit-logs?limit=5")
        record("audit log", "PASS" if status == 200 else "FAIL",
               f"total={(body or {}).get('total')}")

    packages = ai.get("packages", {})
    if packages.get("torch") and packages.get("sentence_transformers"):
        status, body = request(
            "POST", f"{api}/embeddings", {"texts": ["hello", "world"]}, timeout=600
        )
        record(
            "embeddings",
            "PASS" if status == 200 else "FAIL",
            f"HTTP {status} dimension={(body or {}).get('dimension')}",
        )
    else:
        record("embeddings", "SKIP", "torch/sentence-transformers not installed")

    configured = ai.get("llm", {}).get("configured")
    if args.with_llm and configured:
        status, body = request(
            "POST",
            f"{api}/llm/chat",
            {"messages": [{"role": "user", "content": "Reply with: ok"}], "max_output_tokens": 64},
        )
        detail = f"HTTP {status} finish={(body or {}).get('finish_reason')}"
        if status != 200:
            detail += f" error={(body or {}).get('error', {}).get('code')}"
        record("llm chat (ollama)", "PASS" if status == 200 else "FAIL", detail)
    else:
        reason = "not configured" if not configured else "pass --with-llm to call Ollama"
        record("llm chat", "SKIP", reason)

    failed = [r for r in results if r[1] == "FAIL"]
    print(f"\n{len(results) - len(failed)} ok/skipped, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
