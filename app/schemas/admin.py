import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    action: str
    category: str
    target_type: str | None
    target_id: str | None
    outcome: str
    ip_address: str | None
    request_id: str | None
    details: dict[str, Any]


class AuditLogList(BaseModel):
    items: list[AuditLogRead]
    total: int
    offset: int
    limit: int


class SystemSettings(BaseModel):
    allow_self_registration: bool
    maintenance_mode: bool
    announcement_banner: str


class SystemSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allow_self_registration: bool | None = None
    maintenance_mode: bool | None = None
    announcement_banner: str | None = Field(default=None, max_length=500)


class RegistrationStatus(BaseModel):
    allow_self_registration: bool
    # Roles a public sign-up may choose right now. 'admin'/'super_admin' appear only until
    # their one-time account has been created.
    available_roles: list[str]
