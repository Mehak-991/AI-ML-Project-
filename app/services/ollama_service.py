"""Ollama connectivity helpers — no OpenAI dependency."""

import os

import httpx

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def check_ollama_connection() -> dict:
    """
    Verify that the local Ollama service is reachable.

    Returns a dict with status, base_url, and model fields.
    The local Ollama service must already be running before calling this.
    No models are downloaded automatically.
    """
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        response.raise_for_status()
        available = [m["name"] for m in response.json().get("models", [])]
        model_available = OLLAMA_MODEL in available
        return {
            "status": "ok",
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "model_available": model_available,
            "available_models": available,
        }
    except Exception as exc:
        return {
            "status": "error",
            "base_url": OLLAMA_BASE_URL,
            "model": OLLAMA_MODEL,
            "detail": str(exc),
        }
