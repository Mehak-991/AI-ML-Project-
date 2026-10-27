"""Application exception hierarchy.

Raise these from services and routes; the handlers in `app.core.error_handlers`
turn them into a consistent JSON error envelope.
"""

from typing import Any


class ConfigurationError(RuntimeError):
    """Raised at startup when settings are missing or invalid."""


class AppError(Exception):
    """Base class for errors that are safe to show to API clients."""

    status_code: int = 400
    code: str = "app_error"
    message: str = "The request could not be processed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "A required service is currently unavailable."


class DatabaseNotConfiguredError(ServiceUnavailableError):
    code = "database_not_configured"
    message = "The database is not configured."
