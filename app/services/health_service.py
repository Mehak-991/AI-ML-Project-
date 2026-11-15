"""Health and readiness checks."""

from datetime import UTC, datetime
from typing import Any

from app import __version__
from app.core.config import Settings
from app.database import session as db_session
from app.schemas.health import (
    ComponentState,
    DatabaseHealthResponse,
    HealthResponse,
    ReadinessResponse,
)

OPTIONAL_COMPONENTS = ("llm",)


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


def llm_state(settings: Settings, ai: Any | None) -> ComponentState:
    if not settings.OLLAMA_HEALTHCHECK_ENABLED or ai is None:
        return "disabled"
    health = ai.llm_health()
    if not health.get("reachable"):
        return "unavailable"
    return "ok" if health.get("model_available") else "model_missing"


def get_database_health(settings: Settings) -> DatabaseHealthResponse:
    if settings.DATABASE_URL is None:
        return DatabaseHealthResponse(status="not_configured")
    diagnostics = db_session.diagnose_database()
    return DatabaseHealthResponse(
        status="ok" if diagnostics.ok else "unavailable",
        # Category only (e.g. "connection_refused"); never the URL or driver message.
        category=None if diagnostics.ok else diagnostics.category,
        latency_ms=diagnostics.latency_ms,
    )


def get_readiness(settings: Settings, ai: Any | None = None) -> ReadinessResponse:
    """Process is up and its required dependencies are reachable."""
    components = {"database": database_state(settings), "llm": llm_state(settings, ai)}
    required = {k: v for k, v in components.items() if k not in OPTIONAL_COMPONENTS}
    status = "unavailable" if "unavailable" in required.values() else "ok"
    return ReadinessResponse(
        status=status,
        name=settings.APP_NAME,
        version=__version__,
        environment=settings.APP_ENV,
        timestamp=datetime.now(UTC),
        components=components,
        optional_components=list(OPTIONAL_COMPONENTS),
    )
