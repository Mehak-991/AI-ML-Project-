"""Application exception hierarchy.

Raise these from services and routes; the handlers in `app.core.error_handlers`
turn them into a consistent JSON error envelope.
"""

from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException


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
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        self.headers = headers
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


# --- AI / LLM ---------------------------------------------------------------------


class OptionalDependencyMissingError(ServiceUnavailableError):
    code = "optional_dependency_missing"
    message = "An optional AI dependency is not installed."


class ModelLoadError(ServiceUnavailableError):
    code = "model_load_failed"
    message = "The AI model could not be loaded."


class InferenceTimeoutError(AppError):
    status_code = 504
    code = "inference_timeout"
    message = "Model inference did not finish in time."


class ProviderNotConfiguredError(ServiceUnavailableError):
    code = "provider_not_configured"
    message = "The LLM provider is not configured."


class ProviderError(AppError):
    """Upstream LLM provider failure. Messages never include provider payloads or keys."""

    status_code = 502
    code = "provider_error"
    message = "The LLM provider returned an error."


class ProviderAuthenticationError(ProviderError):
    code = "provider_authentication_failed"
    message = "The LLM provider rejected the configured credentials. Check OPENAI_API_KEY."


class ProviderRateLimitError(ProviderError):
    status_code = 429
    code = "provider_rate_limited"
    message = "The LLM provider rate limit was reached. Retry later."


class ProviderQuotaExceededError(ProviderError):
    status_code = 429
    code = "provider_quota_exceeded"
    message = "The LLM provider account has no remaining quota. Check billing."


class ProviderTimeoutError(ProviderError):
    status_code = 504
    code = "provider_timeout"
    message = "The LLM provider did not respond in time."


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
    message = "The LLM provider could not be reached or is temporarily unavailable."


class ProviderRequestRejectedError(ProviderError):
    status_code = 422
    code = "provider_rejected_request"
    message = "The LLM provider rejected the request."


# --- HTTP hardening / persistence ----------------------------------------------------


class RequestTooLargeError(StarletteHTTPException):
    """Raised while the body is being read. It must be an HTTPException: FastAPI turns
    any other exception raised during body parsing into a generic 400."""

    error_code = "request_too_large"

    def __init__(self, message: str = "The request body exceeds the allowed size.") -> None:
        super().__init__(status_code=413, detail=message)


class DatabaseUnavailableError(ServiceUnavailableError):
    code = "database_unavailable"
    message = "The database is temporarily unavailable. Retry later."


class ModelIncompatibleError(AppError):
    status_code = 409
    code = "model_incompatible"
    message = "The stored model is incompatible with this server. Retrain it."
