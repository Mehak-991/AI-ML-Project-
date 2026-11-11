import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    action: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    target_id: uuid.UUID | None
    target_email: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    detail: str | None
    request_id: str | None
    client_ip: str | None


class AuditLogList(BaseModel):
    items: list[AuditLogRead]
    total: int
    offset: int
    limit: int
