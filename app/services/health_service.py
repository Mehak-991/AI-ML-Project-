"""Health and readiness checks."""

from datetime import UTC, datetime

from app import __version__
from app.core.config import Settings
from app.database import session as db_session
from app.schemas.health import ComponentState, HealthResponse, ReadinessResponse


def get_liveness(settings: Settings) -> HealthResponse:
    """Process is up. Does not touch external dependencies."""
    return HealthResponse(
        status="ok",
        name=settings.APP_NAME,
        version=__version__,
        environment=settings.APP_ENV,
        timestamp=datetime.now(UTC),
    )


def database_state(settings: Settings) -> ComponentState:
    if settings.DATABASE_URL is None:
        return "not_configured"
    return "ok" if db_session.check_database_connection() else "unavailable"


def get_readiness(settings: Settings) -> ReadinessResponse:
    """Process is up and its configured dependencies are reachable."""
    components = {"database": database_state(settings)}
    status = "unavailable" if "unavailable" in components.values() else "ok"
    return ReadinessResponse(
        status=status,
        name=settings.APP_NAME,
        version=__version__,
        environment=settings.APP_ENV,
        timestamp=datetime.now(UTC),
        components=components,
    )
