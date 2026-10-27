"""Centralized exception handlers producing a uniform error response."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import (
    DBAPIError,
    DisconnectionError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
)
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError, ConflictError, DatabaseUnavailableError
from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body, exclude_none=True),
        headers=headers,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc.status_code, exc.code, exc.message, exc.details, headers=exc.headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    try:
        default_message = HTTPStatus(exc.status_code).phrase
    except ValueError:
        default_message = "HTTP error"
    message = exc.detail if isinstance(exc.detail, str) else default_message
    code = getattr(exc, "error_code", None) or default_message.lower().replace(" ", "_").replace(
        "-", "_"
    )
    return _error_response(exc.status_code, code, message, headers=exc.headers)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Echo only field locations and messages, never the submitted input values.
    details = [
        {"loc": list(error.get("loc", ())), "msg": error.get("msg", ""), "type": error.get("type")}
        for error in exc.errors()
    ]
    return _error_response(422, "validation_error", "Request validation failed.", details)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to the server log; the client gets a generic message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(500, "internal_server_error", "An unexpected error occurred.")


async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Connection-level failures become 503 (retryable); constraint violations 409.

    The driver message (which can include host names and SQL) is only logged.
    """
    if isinstance(exc, IntegrityError):
        logger.warning("Integrity error on %s %s", request.method, request.url.path)
        conflict = ConflictError("The request conflicts with existing data.")
        return _error_response(conflict.status_code, conflict.code, conflict.message)
    if isinstance(exc, OperationalError | InterfaceError | DisconnectionError) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    ):
        logger.error(
            "Database unavailable on %s %s: %s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        error = DatabaseUnavailableError()
        return _error_response(error.status_code, error.code, error.message)
    return await unhandled_exception_handler(request, exc)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
