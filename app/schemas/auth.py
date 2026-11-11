import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator

from app.core.permissions import effective_role, permission_names

# Every role the API can return.
UserRole = Literal["user", "admin", "superadmin"]
# Roles an administrator-facing request may assign. "superadmin" is deliberately absent: it can
# only be granted through the dedicated grant endpoint by an existing superadmin, or by the
# server-side bootstrap CLI.
AssignableRole = Literal["user", "admin"]


class UserRegisterRequest(BaseModel):
    """Public self-registration. It has no role field on purpose: it always creates a ``user``,
    and ``extra="forbid"`` turns any attempt to send one into a validation error."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)


class UserCreateRequest(BaseModel):
    """Account creation by a superadmin."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    role: AssignableRole = "user"


class SelfUpdateRequest(BaseModel):
    """What a user may change about their own profile. Never a role or status."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=255)


class UserLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(max_length=1024)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    user: "UserRead"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    # The effective role: accounts still stored with a legacy name are reported with the
    # current one, so clients only ever see "user", "admin" or "superadmin".
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _report_effective_role(cls, stored: object) -> object:
        resolved = effective_role(stored) if isinstance(stored, str) else None
        return resolved.value if resolved is not None else stored

    @computed_field  # type: ignore[prop-decorator]
    @property
    def permissions(self) -> list[str]:
        """Computed on the server from the permission registry; the UI must not keep its own copy."""
        return permission_names(self.role)


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AssignableRole | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)


class UserList(BaseModel):
    items: list[UserRead]
    total: int
    offset: int
    limit: int
