import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import JSONType


class AuditLog(Base):
    """Append-only record of security-relevant and privileged operations.

    Deliberately has no foreign keys: actor and target are stored as plain ids plus an email
    snapshot, so entries survive account deletion and the table can be made immutable at the
    database level (an ON DELETE SET NULL action would itself be an UPDATE). On PostgreSQL,
    migration 0014 installs triggers that reject UPDATE, DELETE and TRUNCATE.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # "user.role_changed", "user.deactivated", "superadmin.granted", "cli.superadmin_bootstrap", ...
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    target_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
