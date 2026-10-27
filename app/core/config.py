"""Application settings loaded from environment variables and an optional .env file."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.exceptions import ConfigurationError

Environment = Literal["development", "testing", "production"]

DEFAULT_DEV_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class Settings(BaseSettings):
    """Typed application configuration.

    Values are read from environment variables first, then from `.env`.
    Secrets are stored as `SecretStr` so they never appear in logs or reprs.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "AIProject"
    APP_ENV: Environment = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Comma-separated in the environment, e.g. "https://a.com,https://b.com".
    # None means "use the environment's default" (empty list in production).
    CORS_ORIGINS: Annotated[list[str] | None, NoDecode] = None

    DATABASE_URL: SecretStr | None = None
    DATABASE_CONNECT_TIMEOUT: int = Field(default=5, ge=1, le=60)

    OPENAI_API_KEY: SecretStr | None = None

    @field_validator("API_V1_PREFIX")
    @classmethod
    def _validate_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/") or value == "/":
            raise ValueError("API_V1_PREFIX must start with '/' and not be the root path")
        return value.rstrip("/")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("DATABASE_URL", "OPENAI_API_KEY", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        url = value.get_secret_value().strip()
        # Plain postgres URLs would make SQLAlchemy look for psycopg2; use psycopg 3.
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url[len(prefix) :]
                break
        return SecretStr(url)

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if self.DATABASE_URL is None:
            problems.append("DATABASE_URL is required when APP_ENV=production")
        if self.DEBUG:
            problems.append("DEBUG must be false when APP_ENV=production")
        if self.CORS_ORIGINS and "*" in self.CORS_ORIGINS:
            problems.append("CORS_ORIGINS must not contain '*' when APP_ENV=production")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Effective CORS origins: explicit value, else a restrictive per-env default."""
        if self.CORS_ORIGINS is not None:
            return self.CORS_ORIGINS
        return [] if self.is_production else list(DEFAULT_DEV_CORS_ORIGINS)


def load_settings(**overrides: object) -> Settings:
    """Build settings, converting validation failures into a readable ConfigurationError."""
    try:
        return Settings(**overrides)
    except ValidationError as exc:
        messages = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "settings"
            messages.append(f"{location}: {error['msg']}")
        raise ConfigurationError("Invalid configuration -> " + " | ".join(messages)) from None


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance for use as a FastAPI dependency."""
    return load_settings()
