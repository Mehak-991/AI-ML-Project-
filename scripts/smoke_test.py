"""End-to-end smoke test against a RUNNING server (local, Docker or deployed).

Usage: python scripts/smoke_test.py [http://127.0.0.1:8000] [--with-llm]

Steps: health -> readiness -> AI status -> token count -> (if the DB is up)
upload synthetic CSV -> train -> model metadata -> predict -> (if local NLP extras
are installed) embeddings -> (only with --with-llm, which costs money) one short
chat completion. Uses only the standard library. Exit code 1 if any step FAILs.
"""

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


def request(
    method: str, url: str, body: Any = None, *, files: dict | None = None, timeout: float = 120
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
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
    parser.add_argument("--with-llm", action="store_true", help="make one real (paid) LLM call")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    api = f"{base}/api/v1"

    status, body = request("GET", f"{base}/health")
    record("liveness", "PASS" if status == 200 else "FAIL", f"HTTP {status}")
    if status != 200:
        return 1

    status, body = request("GET", f"{api}/health")
    db_state = (body or {}).get("components", {}).get("database")
    record("readiness", "PASS" if status in (200, 503) else "FAIL", f"database={db_state}")

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
        record("llm chat (paid)", "PASS" if status == 200 else "FAIL", detail)
    else:
        reason = "not configured" if not configured else "pass --with-llm to make a paid call"
        record("llm chat", "SKIP", reason)

    failed = [r for r in results if r[1] == "FAIL"]
    print(f"\n{len(results) - len(failed)} ok/skipped, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
