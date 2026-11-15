"""Employee request/response schemas.

Two read models: `EmployeeRead` (every role) and `EmployeeReadSensitive` (adds phone and
salary; only for roles holding employees:read_sensitive). Write models forbid unknown
fields, so clients cannot mass-assign ids, audit columns or anything else not listed.
"""

import re
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

EmploymentStatus = Literal["active", "on_leave", "terminated"]

_PHONE = re.compile(r"^\+?[0-9 ()-]{6,32}$")
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Salary = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"), decimal_places=2)]


def _check_phone(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _PHONE.match(value):
        raise ValueError("Phone may contain digits, spaces, parentheses, dashes and a leading +.")
    return value


def _check_hire_date(value: date | None) -> date | None:
    # Allow future-dated hires up to a year ahead (accepted offers), nothing absurd.
    if value is not None and (value.year < 1900 or value > date.today() + timedelta(days=366)):
        raise ValueError("hire_date must be between 1900 and one year from today.")
    return value


class _EmployeeFieldChecks(BaseModel):
    @field_validator("phone", check_fields=False)
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return _check_phone(value)

    @field_validator("hire_date", check_fields=False)
    @classmethod
    def _hire_date(cls, value: date | None) -> date | None:
        return _check_hire_date(value)


class EmployeeCreate(_EmployeeFieldChecks):
    model_config = ConfigDict(extra="forbid")

    employee_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    first_name: Name
    last_name: Name
    email: EmailStr
    department: Name
    job_title: Title
    employment_status: EmploymentStatus = "active"
    hire_date: date
    phone: str | None = Field(default=None, max_length=32)
    salary: Salary | None = None
    manager_id: uuid.UUID | None = None

    @field_validator("employee_code")
    @classmethod
    def _code(cls, value: str) -> str:
        if not _CODE.match(value):
            raise ValueError("employee_code may contain letters, digits, '-' and '_' only.")
        return value.upper()



class EmployeeUpdate(_EmployeeFieldChecks):
    """Partial update. employee_code is immutable once created."""

    model_config = ConfigDict(extra="forbid")

    first_name: Name | None = None
    last_name: Name | None = None
    email: EmailStr | None = None
    department: Name | None = None
    job_title: Title | None = None
    employment_status: EmploymentStatus | None = None
    hire_date: date | None = None
    phone: str | None = Field(default=None, max_length=32)
    salary: Salary | None = None
    manager_id: uuid.UUID | None = None



class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    email: str
    department: str
    job_title: str
    employment_status: EmploymentStatus
    hire_date: date
    manager_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class EmployeeReadSensitive(EmployeeRead):
    phone: str | None
    salary: Decimal | None
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class EmployeeList(BaseModel):
    items: list[EmployeeReadSensitive] | list[EmployeeRead]
    total: int
    offset: int
    limit: int
    sensitive_fields_included: bool


class EmployeeStats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_department: dict[str, int]
