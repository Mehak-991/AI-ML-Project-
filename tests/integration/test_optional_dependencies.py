"""The core API must start and serve without any optional AI package or API key.

Runs a fresh interpreter in which every optional AI package is made
unimportable (even if installed in this venv), then exercises the app.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = r"""
import importlib.abc, json, sys

BLOCKED = {"torch", "torchvision", "transformers", "sentence_transformers", "datasets",
           "evaluate", "openai", "tiktoken", "langgraph", "langchain_core",
           "langchain_text_splitters", "llama_index"}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError(f"blocked for test: {name}")
        return None

sys.meta_path.insert(0, Blocker())

from fastapi.testclient import TestClient
from app.main import create_app

out = {}
with TestClient(create_app()) as client:
    def call(method, path, body=None):
        r = client.request(method, path, json=body)
        return {"status": r.status_code, "body": r.json()}
    out["health"] = call("GET", "/health")
    out["status"] = call("GET", "/api/v1/ai/status")
    out["embeddings"] = call("POST", "/api/v1/embeddings", {"texts": ["hi"]})
    out["classify"] = call("POST", "/api/v1/nlp/classify", {"texts": ["hi"]})
    chat_body = {"messages": [{"role": "user", "content": "hi"}]}
    out["chat"] = call("POST", "/api/v1/llm/chat", chat_body)
    out["tokens"] = call("POST", "/api/v1/tokens/count", {"text": "abcdefgh"})
out["loaded"] = sorted(m for m in BLOCKED if m in sys.modules)
print(json.dumps(out))
"""


def test_core_api_runs_without_optional_ai_packages(tmp_path) -> None:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("OPENAI_", "DATABASE_", "AI_", "EMBEDDING_", "CLASSIFIER_"))
    }
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=tmp_path,  # no .env here
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])

    assert out["health"]["status"] == 200
    assert out["status"]["status"] == 200
    assert not any(out["status"]["body"]["packages"].values())
    assert out["status"]["body"]["llm"]["configured"] is False

    for name in ("embeddings", "classify"):
        assert out[name]["status"] == 503
        assert out[name]["body"]["error"]["code"] == "optional_dependency_missing"
    assert out["chat"]["status"] == 503
    assert out["chat"]["body"]["error"]["code"] == "provider_not_configured"

    assert out["tokens"]["status"] == 200
    assert out["tokens"]["body"] == {
        "model": "gpt-5.4-mini",
        "encoding": "approximate",
        "tokens": 2,
        "approximate": True,
    }
    assert out["loaded"] == []
