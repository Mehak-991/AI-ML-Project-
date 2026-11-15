"""Versioned readiness endpoints, including dependency checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings, get_settings
from app.schemas.health import DatabaseHealthResponse, ReadinessResponse
from app.services import health_service

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=ReadinessResponse,
    summary="Readiness probe (database required; Ollama reported but optional)",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
)
def readiness(
    request: Request, response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> ReadinessResponse:
    ai = getattr(request.app.state, "ai", None)
    result = health_service.get_readiness(settings, ai)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/health/database",
    response_model=DatabaseHealthResponse,
    summary="Database connectivity check with latency",
    responses={503: {"model": DatabaseHealthResponse, "description": "Database unavailable"}},
)
def database_health(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> DatabaseHealthResponse:
    result = health_service.get_database_health(settings)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
