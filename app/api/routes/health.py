"""Versioned readiness endpoint, including dependency checks."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings, get_settings
from app.schemas.health import ReadinessResponse
from app.services import health_service

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
)
def readiness(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> ReadinessResponse:
    result = health_service.get_readiness(settings)
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
