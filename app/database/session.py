"""Engine and session management.

The engine is created lazily so the application can start (and serve health
checks) even when no database is configured or reachable.
"""

import logging
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
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
    connect_args = {}
    if url.startswith("postgresql"):
        connect_args["connect_timeout"] = settings.DATABASE_CONNECT_TIMEOUT
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    """FastAPI dependency yielding a session that is always closed afterwards."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_connection() -> bool:
    """Return True if a trivial query succeeds. Raises if the DB is not configured."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        logger.warning("Database connectivity check failed", exc_info=True)
        return False


def dispose_engine() -> None:
    """Close pooled connections, if an engine was ever created."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
