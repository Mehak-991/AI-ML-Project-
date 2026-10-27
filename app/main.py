"""FastAPI application factory and ASGI entry point (`uvicorn app.main:app`)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.ai.container import AIServices
from app.api.router import COMMON_ERROR_RESPONSES, api_v1_router
from app.api.routes import root
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.database.session import dispose_engine
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s v%s", app.title, __version__)
    yield
    app.state.ai.shutdown()
    dispose_engine()
    logger.info("Shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pass `settings` to override environment config (tests)."""
    settings = settings or get_settings()
    # DEBUG only makes logging verbose. Tracebacks go to the server log, never to clients.
    configure_logging("DEBUG" if settings.DEBUG else settings.LOG_LEVEL, settings.LOG_FORMAT)

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="Modular AI/ML platform API.",
        # Starlette's debug mode returns full tracebacks in 500 responses; keep it off.
        debug=False,
        lifespan=lifespan,
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        redoc_url="/redoc" if settings.DOCS_ENABLED else None,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    # Lazy container: no optional package is imported and no model is loaded here.
    app.state.ai = AIServices(settings)

    # add_middleware wraps: the LAST one added runs FIRST. Resulting order per request:
    # RequestContext -> SecurityHeaders -> CORS -> RateLimit -> BodySizeLimit -> app,
    # so 413/429 responses still get a request ID, security and CORS headers.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=settings.max_request_body_bytes,
        max_upload_bytes=settings.max_upload_bytes,
    )
    if settings.RATE_LIMIT_ENABLED:
        app.add_middleware(
            RateLimitMiddleware,
            api_prefix=settings.API_V1_PREFIX,
            default_per_minute=settings.RATE_LIMIT_DEFAULT_PER_MINUTE,
            ai_per_minute=settings.RATE_LIMIT_AI_PER_MINUTE,
            training_per_minute=settings.RATE_LIMIT_TRAINING_PER_MINUTE,
        )
    origins = settings.cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            # Browsers reject credentials with a wildcard origin.
            allow_credentials="*" not in origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    app.add_middleware(SecurityHeadersMiddleware, api_prefix=settings.API_V1_PREFIX)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(root.router, responses={500: COMMON_ERROR_RESPONSES[500]})
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
