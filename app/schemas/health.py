"""Health check response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ComponentState = Literal["ok", "unavailable", "not_configured", "model_missing", "disabled"]


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    name: str
    version: str
    environment: str
    timestamp: datetime


class ReadinessResponse(HealthResponse):
    components: dict[str, ComponentState]
    # Components reported for information only; they never make readiness fail
    # (the API serves everything except LLM features without Ollama).
    optional_components: list[str] = []


class DatabaseHealthResponse(BaseModel):
    status: ComponentState
    category: str | None = None
    latency_ms: float | None = None
