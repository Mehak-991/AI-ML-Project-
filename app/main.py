"""FastAPI application factory and ASGI entry point (`uvicorn app.main:app`)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_v1_router
from app.api.routes import root
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.database.session import dispose_engine
from app.utils.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s v%s", app.title, __version__)
    yield
    dispose_engine()
    logger.info("Shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pass `settings` to override environment config (tests)."""
    settings = settings or get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title=settings.APP_NAME,
        version=__version__,
        description="Modular AI/ML platform API.",
        debug=settings.DEBUG,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.dependency_overrides[get_settings] = lambda: settings

    origins = settings.cors_origins
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            # Browsers reject credentials with a wildcard origin.
            allow_credentials="*" not in origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
        )

    register_exception_handlers(app)
    app.include_router(root.router)
    app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()
