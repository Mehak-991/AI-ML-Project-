"""ORM models.

Import every model module here so `Base.metadata` is complete for Alembic
autogenerate, e.g. `from app.database.models.user import User  # noqa: F401`.
"""

from app.database.base import Base

__all__ = ["Base"]
