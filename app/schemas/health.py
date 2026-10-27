"""Health check response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ComponentState = Literal["ok", "unavailable", "not_configured"]


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    name: str
    version: str
    environment: str
    timestamp: datetime


class ReadinessResponse(HealthResponse):
    components: dict[str, ComponentState]
