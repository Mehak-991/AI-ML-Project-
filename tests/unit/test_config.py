from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_settings
from app.core.exceptions import ConfigurationError

SettingsFactory = Callable[..., Settings]


def test_defaults_are_safe(make_settings: SettingsFactory) -> None:
    settings = make_settings()
    assert settings.APP_ENV == "development"
    assert settings.DEBUG is False
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.DATABASE_URL is None
    assert settings.OPENAI_API_KEY is None


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "FromEnv")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    settings = Settings(_env_file=None)
    assert settings.APP_NAME == "FromEnv"
    assert settings.DEBUG is True
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_reads_dotenv_file(tmp_path, make_settings: SettingsFactory) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=FromDotenv\nAPI_V1_PREFIX=/api/v2/\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.APP_NAME == "FromDotenv"
    assert settings.API_V1_PREFIX == "/api/v2"


def test_secrets_are_masked(make_settings: SettingsFactory) -> None:
    settings = make_settings(
        OPENAI_API_KEY="sk-test-not-real",
        DATABASE_URL="postgresql://user:hunter2@localhost/db",
    )
    dumped = repr(settings) + str(settings.model_dump())
    assert "sk-test-not-real" not in dumped
    assert "hunter2" not in dumped


def test_postgres_url_is_normalized_to_psycopg(make_settings: SettingsFactory) -> None:
    settings = make_settings(DATABASE_URL="postgres://u:p@localhost:5432/db")
    assert settings.DATABASE_URL.get_secret_value() == "postgresql+psycopg://u:p@localhost:5432/db"


def test_blank_secret_values_become_none(make_settings: SettingsFactory) -> None:
    settings = make_settings(DATABASE_URL="  ", OPENAI_API_KEY="")
    assert settings.DATABASE_URL is None
    assert settings.OPENAI_API_KEY is None


def test_cors_defaults_per_environment(make_settings: SettingsFactory) -> None:
    assert make_settings().cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
    prod = make_settings(APP_ENV="production", DATABASE_URL="postgresql://u:p@h/db")
    assert prod.cors_origins == []


def test_valid_production_settings(make_settings: SettingsFactory) -> None:
    settings = make_settings(
        APP_ENV="production",
        DATABASE_URL="postgresql://u:p@h/db",
        CORS_ORIGINS="https://app.example",
    )
    assert settings.is_production


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"APP_ENV": "production"}, "DATABASE_URL is required"),
        (
            {"APP_ENV": "production", "DATABASE_URL": "postgresql://u:p@h/db", "DEBUG": True},
            "DEBUG must be false",
        ),
        (
            {"APP_ENV": "production", "DATABASE_URL": "postgresql://u:p@h/db", "CORS_ORIGINS": "*"},
            "must not contain '*'",
        ),
        ({"APP_ENV": "staging"}, "APP_ENV"),
        ({"API_V1_PREFIX": "api"}, "API_V1_PREFIX must start with '/'"),
        ({"DEBUG": "not-a-bool"}, "DEBUG"),
    ],
)
def test_invalid_configuration_is_rejected(
    make_settings: SettingsFactory, overrides: dict, expected: str
) -> None:
    with pytest.raises(ValidationError, match=expected):
        make_settings(**overrides)


def test_load_settings_raises_clear_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    with pytest.raises(ConfigurationError) as exc_info:
        load_settings(_env_file=None)
    message = str(exc_info.value)
    assert "Invalid configuration" in message
    assert "DATABASE_URL is required when APP_ENV=production" in message
    assert "sk-should-not-leak" not in message
