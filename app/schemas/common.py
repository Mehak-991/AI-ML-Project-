"""Shared response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, client-safe message.")
    details: Any | None = Field(default=None, description="Optional structured details.")


class ErrorResponse(BaseModel):
    error: ErrorBody


class RootResponse(BaseModel):
    message: str
    name: str
    version: str
    docs_url: str
    health_url: str
