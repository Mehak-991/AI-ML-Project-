"""Database configuration — supports SQLite (default) and PostgreSQL."""

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Read DATABASE_URL from environment; fall back to a local SQLite file.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aiml.db")

# SQLite requires check_same_thread=False for multi-threaded use in FastAPI.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


def get_db():
    """FastAPI dependency — yields a database session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_connection() -> dict:
    """Return a dict describing whether the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "url": DATABASE_URL}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}

