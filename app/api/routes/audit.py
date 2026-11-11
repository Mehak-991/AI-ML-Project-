"""Audit log read access (superadmin only). The trail is append-only: there is no write route."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession, require_permission
from app.core.permissions import Permission
from app.database.models.user import User
from app.schemas.audit import AuditLogList, AuditLogRead
from app.schemas.common import ErrorResponse
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["audit"])

AuditReaderDep = Annotated[User, Depends(require_permission(Permission.AUDIT_READ))]


@router.get(
    "",
    response_model=AuditLogList,
    summary="List audit log entries, newest first (superadmin only)",
    responses={
        401: {"model": ErrorResponse, "description": "Authentication required"},
        403: {"model": ErrorResponse, "description": "Superadmin permission required"},
    },
)
def list_audit_logs(
    _actor: AuditReaderDep,
    db: DbSession,
    action: Annotated[str | None, Query(max_length=64)] = None,
    target_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditLogList:
    items, total = audit_service.list_entries(
        db, action=action, target_id=target_id, actor_id=actor_id, offset=offset, limit=limit
    )
    return AuditLogList(
        items=[AuditLogRead.model_validate(entry) for entry in items],
        total=total,
        offset=offset,
        limit=limit,
    )
