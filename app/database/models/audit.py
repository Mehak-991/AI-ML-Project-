"""Append-only audit trail for security-relevant and data-changing operations."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import JSONType

# Categories drive who may read an entry: admins see the domain categories, super admins
# see everything (account administration, authentication and settings changes included).
AUDIT_CATEGORIES = ("auth", "user_admin", "employee", "ml", "settings")
DOMAIN_AUDIT_CATEGORIES = ("employee", "ml")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_category_created_at", "category", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # Snapshot of the actor: entries stay meaningful after the account is deleted.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(32))
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="success", server_default="success")
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Never contains secrets (passwords, tokens) — see audit_service._scrub.
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
