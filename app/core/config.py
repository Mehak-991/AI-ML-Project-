"""Application settings loaded from environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
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
    # "json" = one JSON object per line (for log shippers); "text" = human-readable.
    LOG_FORMAT: Literal["text", "json"] = "text"
    DOCS_ENABLED: bool = True

    # Request hardening
    MAX_REQUEST_BODY_MB: float = Field(default=5, gt=0, le=1024)  # non-upload requests
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_PER_MINUTE: int = Field(default=300, ge=1)
    RATE_LIMIT_AI_PER_MINUTE: int = Field(default=30, ge=1)
    RATE_LIMIT_TRAINING_PER_MINUTE: int = Field(default=10, ge=1)

    # Comma-separated in the environment, e.g. "https://a.com,https://b.com".
    # None means "use the environment's default" (empty list in production).
    CORS_ORIGINS: Annotated[list[str] | None, NoDecode] = None

    DATABASE_URL: SecretStr | None = None
    DATABASE_CONNECT_TIMEOUT: int = Field(default=5, ge=1, le=60)
    DATABASE_POOL_SIZE: int = Field(default=5, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100)
    DATABASE_ECHO: bool = False

    # Server-side storage locations. Never taken from API requests.
    UPLOAD_DIR: Path = Path("uploads")
    MODEL_DIR: Path = Path("trained_models")

    # Data and ML limits.
    MAX_UPLOAD_SIZE_MB: int = Field(default=25, ge=1, le=1024)
    MAX_DATASET_ROWS: int = Field(default=200_000, ge=10)
    MAX_DATASET_COLUMNS: int = Field(default=500, ge=2)
    MAX_PREDICTION_RECORDS: int = Field(default=1000, ge=1)
    # strict: refuse to load artifacts saved with a different scikit-learn major.minor
    # (pickles are not guaranteed compatible); warn: load anyway and log a warning.
    MODEL_COMPATIBILITY_CHECK: Literal["strict", "warn"] = "strict"

    # --- LLM provider. "openai" (hosted, needs OPENAI_API_KEY) or "ollama" (local, free). ---
    # Default stays "openai" so deployments without this setting behave exactly as before.
    LLM_PROVIDER: Literal["openai", "ollama"] = "openai"

    # Ollama (used when LLM_PROVIDER=ollama). No API key involved.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    # Other locally pulled models a request may select (comma-separated).
    OLLAMA_ALLOWED_MODELS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Local CPU inference is slow; this bounds one whole /api/chat call (incl. model load).
    OLLAMA_TIMEOUT_SECONDS: float = Field(default=180.0, gt=0, le=3600)

    # OpenAI (used when LLM_PROVIDER=openai). Optional: the app starts without a key.
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_MODEL: str = "gpt-5.4-mini"
    # Models a request may select; empty means only OPENAI_MODEL.
    OPENAI_ALLOWED_MODELS: Annotated[list[str], NoDecode] = Field(default_factory=list)
    OPENAI_BASE_URL: str | None = None
    OPENAI_ORGANIZATION: str | None = None
    OPENAI_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=600)
    OPENAI_MAX_RETRIES: int = Field(default=2, ge=0, le=10)
    LLM_MAX_MESSAGES: int = Field(default=50, ge=1, le=500)
    LLM_MAX_INPUT_CHARS: int = Field(default=32_000, ge=1)
    LLM_MAX_INPUT_TOKENS: int = Field(default=8_000, ge=1)
    LLM_MAX_OUTPUT_TOKENS: int = Field(default=4_096, ge=16)
    LLM_DEFAULT_OUTPUT_TOKENS: int = Field(default=1_024, ge=16)
    # Prompts/completions are never logged unless this is explicitly enabled.
    LLM_LOG_CONTENT: bool = False

    # --- Local models (Sentence Transformers / Transformers). Loaded lazily. ---
    AI_DEVICE: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    AI_MODEL_CACHE_DIR: Path | None = None  # None = Hugging Face default cache
    AI_ALLOW_MODEL_DOWNLOADS: bool = True
    AI_MAX_LOADED_MODELS: int = Field(default=3, ge=1, le=20)
    AI_INFERENCE_TIMEOUT_SECONDS: float = Field(default=60.0, gt=0, le=3600)
    AI_MAX_CONCURRENT_INFERENCES: int = Field(default=2, ge=1, le=64)

    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    # If set, every embedding must have exactly this many dimensions.
    EMBEDDING_DIMENSION: int | None = Field(default=None, ge=1)
    EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=1024)
    EMBEDDING_MAX_TEXTS: int = Field(default=128, ge=1)
    EMBEDDING_MAX_TEXT_CHARS: int = Field(default=8_000, ge=1)

    CLASSIFIER_MODEL: str = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
    CLASSIFIER_MAX_TEXTS: int = Field(default=64, ge=1)
    CLASSIFIER_MAX_TEXT_CHARS: int = Field(default=4_000, ge=1)

    TOKENIZER_MAX_TEXT_CHARS: int = Field(default=200_000, ge=1)

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

    @field_validator("OLLAMA_BASE_URL")
    @classmethod
    def _validate_ollama_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")
        return value

    @field_validator("OPENAI_ALLOWED_MODELS", "OLLAMA_ALLOWED_MODELS", mode="before")
    @classmethod
    def _split_models(cls, value: object) -> object:
        if isinstance(value, str):
            return [model.strip() for model in value.split(",") if model.strip()]
        return value

    @field_validator(
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORGANIZATION",
        "EMBEDDING_DIMENSION",
        "AI_MODEL_CACHE_DIR",
        mode="before",
    )
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
        elif not self.DATABASE_URL.get_secret_value().startswith("postgresql+psycopg://"):
            problems.append("DATABASE_URL must be a PostgreSQL URL when APP_ENV=production")
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
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_request_body_bytes(self) -> int:
        return int(self.MAX_REQUEST_BODY_MB * 1024 * 1024)

    @property
    def active_llm_model(self) -> str:
        """Default chat model of the selected provider."""
        return self.OLLAMA_MODEL if self.LLM_PROVIDER == "ollama" else self.OPENAI_MODEL

    @property
    def allowed_llm_models(self) -> list[str]:
        """Models a chat request may select, for the selected provider only."""
        extra = (
            self.OLLAMA_ALLOWED_MODELS
            if self.LLM_PROVIDER == "ollama"
            else self.OPENAI_ALLOWED_MODELS
        )
        return list(dict.fromkeys([self.active_llm_model, *extra]))

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
