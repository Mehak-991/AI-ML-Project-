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


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The request conflicts with the current state of the resource."


class InvalidFileError(AppError):
    status_code = 400
    code = "invalid_file"
    message = "The uploaded file is invalid."


class UnsupportedFileTypeError(InvalidFileError):
    status_code = 415
    code = "unsupported_file_type"
    message = "Unsupported file type."


class FileTooLargeError(InvalidFileError):
    status_code = 413
    code = "file_too_large"
    message = "The uploaded file exceeds the size limit."


class DataValidationError(AppError):
    status_code = 422
    code = "data_validation_error"
    message = "The data failed validation."


class TrainingError(AppError):
    status_code = 422
    code = "training_error"
    message = "The model could not be trained on this data."


class ModelArtifactError(AppError):
    status_code = 500
    code = "model_artifact_error"
    message = "The stored model artifact is missing or invalid."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "A required service is currently unavailable."


class DatabaseNotConfiguredError(ServiceUnavailableError):
    code = "database_not_configured"
    message = "The database is not configured."
