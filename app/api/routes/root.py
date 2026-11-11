"""Unversioned endpoints: welcome message and liveness probe."""

from typing import Annotated

import hmac

from fastapi import APIRouter, Depends, Security
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import PublicRoute
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.database.session import get_db
from app.schemas.common import ErrorResponse, RootResponse
from app.schemas.health import HealthResponse
from app.services import health_service

router = APIRouter(tags=["system"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
metrics_bearer = HTTPBearer(auto_error=False)


@router.get("/", response_model=RootResponse, summary="Welcome", dependencies=[PublicRoute])
def read_root(settings: SettingsDep) -> RootResponse:
    return RootResponse(
        message=f"Welcome to {settings.APP_NAME}",
        name=settings.APP_NAME,
        version=__version__,
        docs_url="/docs",
        health_url=f"{settings.API_V1_PREFIX}/health",
    )



@router.get("/health", response_model=HealthResponse, summary="Liveness probe", dependencies=[PublicRoute])
def liveness(settings: SettingsDep) -> HealthResponse:
    return health_service.get_liveness(settings)


@router.get(
    "/metrics",
    dependencies=[PublicRoute],  # protected by its own bearer token (METRICS_TOKEN)
    summary="Prometheus metrics exporter",
    response_class=PlainTextResponse,
    responses={
        200: {
            "content": {"text/plain; version=0.0.4; charset=utf-8": {}},
            "description": "OpenMetrics / Prometheus text representation",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected server error",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
        },
    },
)
def get_metrics(
    settings: SettingsDep,
    auth: Annotated[HTTPAuthorizationCredentials | None, Security(metrics_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> PlainTextResponse:
    """Exposes OpenMetrics / Prometheus formatted text metrics for scraper targets."""
    from app.core.metrics import collect_prometheus_metrics

    if settings.METRICS_TOKEN is not None:
        expected = settings.METRICS_TOKEN.get_secret_value().encode()
        supplied = (auth.credentials if auth else "").encode()
        if not hmac.compare_digest(supplied, expected):
            raise AuthenticationError(
                "A valid metrics token is required.", headers={"WWW-Authenticate": "Bearer"}
            )
    metrics_text = collect_prometheus_metrics(db, settings.WORKER_HEARTBEAT_FILE)
    return PlainTextResponse(
        content=metrics_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

