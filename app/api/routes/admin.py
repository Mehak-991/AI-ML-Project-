"""Audit log and global application settings."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbOptionalSession, DbSession, require_permission
from app.core.permissions import Permission
from app.database.models.audit import AUDIT_CATEGORIES
from app.database.models.user import User
from app.schemas.admin import (
    AuditLogList,
    AuditLogRead,
    RegistrationStatus,
    SystemSettings,
    SystemSettingsUpdate,
)
from app.schemas.common import ErrorResponse
from app.services import audit_service, role_slots, settings_service

router = APIRouter(tags=["administration"])

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Role does not permit this action"}}

AuditReader = Annotated[User, Depends(require_permission(Permission.AUDIT_READ))]
SettingsReader = Annotated[User, Depends(require_permission(Permission.SETTINGS_READ))]
SettingsWriter = Annotated[User, Depends(require_permission(Permission.SETTINGS_WRITE))]


@router.get(
    "/audit-logs",
    response_model=AuditLogList,
    summary="Audit trail (Admin: employee and ML events; Super Admin: everything)",
    responses=UNAUTHORIZED | FORBIDDEN,
)
def list_audit_logs(
    user: AuditReader,
    db: DbSession,
    category: Annotated[str | None, Query(pattern="^(" + "|".join(AUDIT_CATEGORIES) + ")$")] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor_id: uuid.UUID | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogList:
    items, total = audit_service.list_entries(
        db,
        user,
        category=category,
        action=action,
        actor_id=actor_id,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )
    return AuditLogList(
        items=[AuditLogRead.model_validate(i) for i in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/settings",
    response_model=SystemSettings,
    summary="Global application settings (read: every signed-in user)",
    responses=UNAUTHORIZED,
)
def get_settings_values(_user: SettingsReader, db: DbSession) -> SystemSettings:
    return SystemSettings(**settings_service.get_all(db))


@router.patch(
    "/settings",
    response_model=SystemSettings,
    summary="Change global application settings (Super Admin only)",
    responses=UNAUTHORIZED | FORBIDDEN,
)
def update_settings_values(
    request: SystemSettingsUpdate, actor: SettingsWriter, db: DbSession
) -> SystemSettings:
    changes = request.model_dump(exclude_unset=True, exclude_none=True)
    return SystemSettings(**settings_service.update(db, actor, changes))


@router.get(
    "/auth/registration-status",
    response_model=RegistrationStatus,
    tags=["auth"],
    summary="Whether public sign-up is open (no authentication)",
)
def registration_status(db: DbOptionalSession) -> RegistrationStatus:
    return RegistrationStatus(
        allow_self_registration=bool(
            settings_service.get_value(db, "allow_self_registration")
        ),
        available_roles=role_slots.available_roles(db),
    )
