"""Engine and session management.

The engine is created lazily so the application can start (and serve health
checks) even when no database is configured or reachable.
"""

import logging
import time
from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import ArgumentError, NoSuchModuleError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.exceptions import DatabaseNotConfiguredError

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if settings.DATABASE_URL is None:
        raise DatabaseNotConfiguredError()
    url = settings.DATABASE_URL.get_secret_value()
    kwargs: dict = {"pool_pre_ping": True, "echo": settings.DATABASE_ECHO}
    if url.startswith("postgresql"):
        kwargs |= {
            "connect_args": {"connect_timeout": settings.DATABASE_CONNECT_TIMEOUT},
            "pool_size": settings.DATABASE_POOL_SIZE,
            "max_overflow": settings.DATABASE_MAX_OVERFLOW,
        }
    return create_engine(url, **kwargs)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """FastAPI dependency yielding a session that is always closed afterwards.

    Services commit explicitly; anything uncommitted is rolled back on error.
    """
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@dataclass(frozen=True)
class DatabaseDiagnostics:
    ok: bool
    category: str
    hint: str
    url: str | None = None
    server_version: str | None = None
    latency_ms: float | None = None


# Substrings of driver error messages -> (category, actionable hint).
_ERROR_PATTERNS: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("password authentication failed", "authentication failed", "no password supplied"),
        "authentication_failed",
        "Check the username and password in DATABASE_URL.",
    ),
    (
        ("does not exist",),
        "database_not_found",
        "Create the database (e.g. `createdb <name>`) or fix the name in DATABASE_URL.",
    ),
    (
        ("connection refused", "actively refused"),
        "connection_refused",
        "PostgreSQL is not accepting connections on that host/port. Is the server running?",
    ),
    (
        ("could not translate host name", "name or service not known", "nodename nor servname"),
        "host_not_found",
        "The database host name could not be resolved.",
    ),
    (
        ("timeout expired", "timed out"),
        "timeout",
        "The connection timed out. Check host, port, firewall and DATABASE_CONNECT_TIMEOUT.",
    ),
]


def _masked_url() -> str | None:
    settings = get_settings()
    if settings.DATABASE_URL is None:
        return None
    try:
        return make_url(settings.DATABASE_URL.get_secret_value()).render_as_string(
            hide_password=True
        )
    except ArgumentError:
        return "<unparseable DATABASE_URL>"


def classify_database_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, NoSuchModuleError | ModuleNotFoundError):
        return "driver_missing", "Install psycopg and use the postgresql+psycopg:// scheme."
    if isinstance(exc, ArgumentError):
        return "invalid_url", "DATABASE_URL is not a valid SQLAlchemy URL."
    message = str(exc).lower()
    for needles, category, hint in _ERROR_PATTERNS:
        if any(needle in message for needle in needles):
            return category, hint
    return "unknown_error", "See the server log for the full driver error."


def diagnose_database() -> DatabaseDiagnostics:
    """Try a round-trip to the database and explain any failure in plain terms.

    Never includes the password; driver messages are logged, not returned.
    """
    url = _masked_url()
    if url is None:
        return DatabaseDiagnostics(False, "not_configured", "Set DATABASE_URL (see .env.example).")
    start = time.perf_counter()
    try:
        engine = get_engine()
        with engine.connect() as connection:
            if engine.dialect.name == "postgresql":
                version = connection.execute(text("SHOW server_version")).scalar()
            else:
                connection.execute(text("SELECT 1"))
                version = engine.dialect.name
    except (SQLAlchemyError, ModuleNotFoundError) as exc:
        logger.warning("Database connectivity check failed: %s", exc)
        category, hint = classify_database_error(exc)
        return DatabaseDiagnostics(False, category, hint, url=url)
    latency = round((time.perf_counter() - start) * 1000, 1)
    return DatabaseDiagnostics(True, "ok", "Connected.", url, str(version), latency)


def check_database_connection() -> bool:
    """Return True if the database answers. Raises if the DB is not configured."""
    get_engine()
    return diagnose_database().ok


def dispose_engine() -> None:
    """Close pooled connections, if an engine was ever created."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
