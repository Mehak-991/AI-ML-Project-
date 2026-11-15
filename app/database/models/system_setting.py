"""Runtime application settings managed by Super Admins (non-secret, typed, whitelisted)."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin
from app.database.types import JSONType


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"

    # Keys are restricted to app.services.settings_service.SETTING_DEFINITIONS.
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
