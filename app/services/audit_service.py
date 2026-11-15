"""Audit trail for sensitive operations.

`record()` adds the entry to the caller's session and does NOT commit, so the audit
row is written in the same transaction as the change it describes: either both are
persisted or neither is. `record_standalone()` commits on its own and is used for
events with no accompanying change (e.g. failed logins), and never raises.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import Permission, has_permission
from app.database.models.audit import AUDIT_CATEGORIES, DOMAIN_AUDIT_CATEGORIES, AuditLog
from app.database.models.user import User
from app.utils.logging import client_ip_var, request_id_var

logger = logging.getLogger("app.audit")

_SECRET_KEYS = ("password", "token", "secret", "hashed_password", "authorization")


def _scrub(value: Any) -> Any:
    """Drop anything that looks like a credential before it reaches the audit table."""
    if isinstance(value, dict):
        return {
            str(k): ("[redacted]" if any(s in str(k).lower() for s in _SECRET_KEYS) else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _build(
    *,
    actor: User | None,
    action: str,
    category: str,
    target_type: str | None,
    target_id: Any,
    details: dict[str, Any] | None,
    outcome: str,
    actor_email: str | None,
) -> AuditLog:
    if category not in AUDIT_CATEGORIES:
        raise ValueError(f"Unknown audit category '{category}'")
    request_id = request_id_var.get()
    return AuditLog(
        id=uuid.uuid4(),
        actor_id=actor.id if actor is not None else None,
        actor_email=(actor.email if actor is not None else actor_email),
        actor_role=actor.role if actor is not None else None,
        action=action,
        category=category,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        outcome=outcome,
        ip_address=client_ip_var.get(),
        request_id=None if request_id == "-" else request_id,
        details=_scrub(details or {}),
    )


def record(
    session: Session,
    *,
    actor: User | None,
    action: str,
    category: str,
    target_type: str | None = None,
    target_id: Any = None,
    details: dict[str, Any] | None = None,
    outcome: str = "success",
    actor_email: str | None = None,
) -> AuditLog:
    """Stage an audit entry in the caller's transaction (caller commits)."""
    entry = _build(
        actor=actor,
        action=action,
        category=category,
        target_type=target_type,
        target_id=target_id,
        details=details,
        outcome=outcome,
        actor_email=actor_email,
    )
    session.add(entry)
    logger.info(
        "audit action=%s category=%s outcome=%s target=%s:%s",
        action,
        category,
        outcome,
        target_type,
        entry.target_id,
        extra={"audit_action": action, "actor_id": str(entry.actor_id) if entry.actor_id else None},
    )
    return entry


def record_standalone(session: Session, **kwargs: Any) -> None:
    """Persist an audit entry in its own transaction. Never raises (best effort)."""
    try:
        record(session, **kwargs)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to write audit entry for action=%s", kwargs.get("action"))


def visible_categories(user: User) -> tuple[str, ...] | None:
    """Categories `user` may read; None = all of them."""
    if has_permission(user.role, Permission.AUDIT_READ_ALL):
        return None
    return DOMAIN_AUDIT_CATEGORIES


def list_entries(
    session: Session,
    user: User,
    *,
    category: str | None = None,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[Sequence[AuditLog], int]:
    stmt = select(AuditLog)
    allowed = visible_categories(user)
    if allowed is not None:
        stmt = stmt.where(AuditLog.category.in_(allowed))
    if category is not None:
        stmt = stmt.where(AuditLog.category == category)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if start_date is not None:
        stmt = stmt.where(AuditLog.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(AuditLog.created_at <= end_date)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = session.scalars(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id).offset(offset).limit(limit)
    ).all()
    return items, total
