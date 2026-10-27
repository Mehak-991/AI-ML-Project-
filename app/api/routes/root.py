"""Unversioned endpoints: welcome message and liveness probe."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import __version__
from app.core.config import Settings, get_settings
from app.schemas.common import RootResponse
from app.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter(tags=["system"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/", response_model=RootResponse, summary="Welcome")
def read_root(settings: SettingsDep) -> RootResponse:
    return RootResponse(
        message=f"Welcome to {settings.APP_NAME}",
        name=settings.APP_NAME,
        version=__version__,
        docs_url="/docs",
        health_url=f"{settings.API_V1_PREFIX}/health",
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def liveness(settings: SettingsDep) -> HealthResponse:
    return health_service.get_liveness(settings)
