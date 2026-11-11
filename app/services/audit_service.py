"""Audit trail for privileged and security-relevant operations.

Entries are added to the caller's session and committed together with the change they
describe, so a role change and its audit record are atomic: both persist or neither does.
Nothing here updates or deletes entries; on PostgreSQL migration 0014 also enforces that with
triggers.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.database.models.audit import AuditLog
from app.database.models.user import User
from app.utils.logging import request_id_var

# Actions that appear in the trail. Kept as constants so tests and the UI can rely on them.
ACTION_USER_REGISTERED = "user.registered"
ACTION_USER_CREATED = "user.created"
ACTION_ROLE_CHANGED = "user.role_changed"
ACTION_DEACTIVATED = "user.deactivated"
ACTION_REACTIVATED = "user.reactivated"
ACTION_PROFILE_UPDATED = "user.profile_updated"
ACTION_DELETED = "user.deleted"
ACTION_SUPERADMIN_GRANTED = "superadmin.granted"
ACTION_SUPERADMIN_REVOKED = "superadmin.revoked"
ACTION_DEPLOYED = "deployment.deployed"
ACTION_UNDEPLOYED = "deployment.undeployed"
ACTION_CLI_BOOTSTRAP = "cli.superadmin_bootstrap"
ACTION_CLI_PASSWORD_RESET = "cli.password_reset"  # noqa: S105 - audit action label, not a password
ACTION_MIGRATION_ROLE_MAPPED = "migration.role_mapped"


@dataclass(frozen=True)
class AuditContext:
    """Where a request came from; copied into every entry written for it."""

    request_id: str | None = None
    client_ip: str | None = None

    @classmethod
    def for_request(cls, client_ip: str | None) -> AuditContext:
        request_id = request_id_var.get()
        return cls(request_id=None if request_id == "-" else request_id, client_ip=client_ip)


def audit_table_exists(session: Session) -> bool:
    """False until migration 0014 has been applied; the CLIs refuse to run before then."""
    return inspect(session.get_bind()).has_table(AuditLog.__tablename__)


def user_snapshot(user: User) -> dict[str, Any]:
    """Non-sensitive account state for before/after comparison (never the password hash)."""
    return {"role": user.role, "is_active": user.is_active, "full_name": user.full_name}


def record(
    session: Session,
    *,
    action: str,
    actor: User | None = None,
    actor_label: str | None = None,
    target: User | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    detail: str | None = None,
    context: AuditContext | None = None,
) -> AuditLog:
    """Add an audit entry to ``session`` (the caller commits)."""
    entry = AuditLog(
        action=action,
        actor_id=actor.id if actor is not None else None,
        actor_email=actor.email if actor is not None else actor_label,
        actor_role=actor.role if actor is not None else None,
        target_id=target.id if target is not None else None,
        target_email=target.email if target is not None else None,
        before=before,
        after=after,
        detail=detail,
        request_id=context.request_id if context else None,
        client_ip=context.client_ip if context else None,
    )
    session.add(entry)
    return entry


def list_entries(
    session: Session,
    *,
    action: str | None = None,
    target_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[Sequence[AuditLog], int]:
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    for column, value in ((AuditLog.action, action), (AuditLog.target_id, target_id), (AuditLog.actor_id, actor_id)):
        if value is not None:
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)
    stmt = stmt.order_by(AuditLog.created_at.desc(), AuditLog.id).offset(offset).limit(limit)
    return session.scalars(stmt).all(), session.scalar(count_stmt) or 0
