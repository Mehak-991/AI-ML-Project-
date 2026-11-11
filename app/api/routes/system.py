"""Read-only view of non-secret runtime settings (superadmin only)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app import __version__
from app.api.deps import SettingsDep, require_permission
from app.core.permissions import Permission
from app.database.models.user import User
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/system", tags=["system"])

SettingsReaderDep = Annotated[User, Depends(require_permission(Permission.SETTINGS_READ))]


class SystemSettingsRead(BaseModel):
    """An explicit allow-list. Secrets (JWT key, database URL, tokens, API keys) are never here;
    only whether a secret-backed feature is configured."""

    app_name: str
    environment: str
    version: str
    release: str | None
    docs_enabled: bool
    log_level: str
    rate_limit_enabled: bool
    rate_limits_per_minute: dict[str, int]
    max_upload_size_mb: float
    max_dataset_rows: int
    max_dataset_columns: int
    max_prediction_records: int
    access_token_minutes: int
    refresh_token_days: int
    job_inline_dispatch: bool
    job_stale_timeout_minutes: int
    database_pool_size: int
    database_max_overflow: int
    metrics_token_configured: bool
    password_rehash_on_login: bool
    rbac_store_legacy_viewer: bool
    llm_provider: str


@router.get(
    "/settings",
    response_model=SystemSettingsRead,
    summary="Non-secret runtime settings (superadmin only, read-only)",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Superadmin permission required"},
    },
)
def read_system_settings(_actor: SettingsReaderDep, settings: SettingsDep) -> SystemSettingsRead:
    return SystemSettingsRead(
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        version=__version__,
        release=settings.APP_RELEASE,
        docs_enabled=settings.DOCS_ENABLED,
        log_level=settings.LOG_LEVEL,
        rate_limit_enabled=settings.RATE_LIMIT_ENABLED,
        rate_limits_per_minute={
            "default": settings.RATE_LIMIT_DEFAULT_PER_MINUTE,
            "ai": settings.RATE_LIMIT_AI_PER_MINUTE,
            "training": settings.RATE_LIMIT_TRAINING_PER_MINUTE,
            "auth": settings.RATE_LIMIT_AUTH_PER_MINUTE,
            "analysis": settings.RATE_LIMIT_ANALYSIS_PER_MINUTE,
        },
        max_upload_size_mb=settings.MAX_UPLOAD_SIZE_MB,
        max_dataset_rows=settings.MAX_DATASET_ROWS,
        max_dataset_columns=settings.MAX_DATASET_COLUMNS,
        max_prediction_records=settings.MAX_PREDICTION_RECORDS,
        access_token_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        refresh_token_days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS,
        job_inline_dispatch=settings.JOB_INLINE_DISPATCH,
        job_stale_timeout_minutes=settings.JOB_STALE_TIMEOUT_MINUTES,
        database_pool_size=settings.DATABASE_POOL_SIZE,
        database_max_overflow=settings.DATABASE_MAX_OVERFLOW,
        metrics_token_configured=settings.METRICS_TOKEN is not None,
        password_rehash_on_login=settings.PASSWORD_REHASH_ON_LOGIN,
        rbac_store_legacy_viewer=settings.RBAC_STORE_LEGACY_VIEWER,
        llm_provider=str(settings.LLM_PROVIDER),
    )
