"""Employee records.

- user:        list/read (phone and salary are omitted)
- admin:       + create and update any record; delete only records they created;
               sees sensitive fields
- super_admin: + delete any record
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import DbSession, require_permission
from app.core.permissions import Permission, has_permission
from app.database.models.employee import Employee
from app.database.models.user import User
from app.repositories.employees import EmployeeRepository, SortField
from app.schemas.common import ErrorResponse
from app.schemas.employees import (
    EmployeeCreate,
    EmployeeList,
    EmployeeRead,
    EmployeeReadSensitive,
    EmployeeStats,
    EmployeeUpdate,
    EmploymentStatus,
)
from app.services import employee_service

router = APIRouter(prefix="/employees", tags=["employees"])

Reader = Annotated[User, Depends(require_permission(Permission.EMPLOYEES_READ))]
Writer = Annotated[User, Depends(require_permission(Permission.EMPLOYEES_WRITE))]
# Route gate: any role that may delete at least its own records. Ownership is enforced in
# employee_service.delete_employee (admins: created_by_id must be the caller).
Deleter = Annotated[User, Depends(require_permission(Permission.EMPLOYEES_DELETE_OWN))]

UNAUTHORIZED = {401: {"model": ErrorResponse, "description": "Authentication required"}}
FORBIDDEN = {403: {"model": ErrorResponse, "description": "Role does not permit this action"}}
NOT_FOUND = {404: {"model": ErrorResponse, "description": "Employee not found"}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Employee code or email already in use"}}


def _present(user: User, employee: Employee) -> EmployeeRead | EmployeeReadSensitive:
    """Serialize with the field set the caller's role is allowed to see."""
    if has_permission(user.role, Permission.EMPLOYEES_READ_SENSITIVE):
        return EmployeeReadSensitive.model_validate(employee)
    return EmployeeRead.model_validate(employee)


@router.get(
    "",
    response_model=EmployeeList,
    summary="List employees with search, filters, sorting and pagination",
    responses=UNAUTHORIZED,
)
def list_employees(
    user: Reader,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    employment_status: EmploymentStatus | None = None,
    manager_id: uuid.UUID | None = None,
    sort: SortField = "last_name",
    descending: bool = False,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> EmployeeList:
    items, total = EmployeeRepository(db).list_filtered(
        search=search,
        department=department,
        status=employment_status,
        manager_id=manager_id,
        sort=sort,
        descending=descending,
        offset=offset,
        limit=limit,
    )
    return EmployeeList(
        items=[_present(user, e) for e in items],
        total=total,
        offset=offset,
        limit=limit,
        sensitive_fields_included=has_permission(
            user.role, Permission.EMPLOYEES_READ_SENSITIVE
        ),
    )


@router.get(
    "/stats",
    response_model=EmployeeStats,
    summary="Headcount by status and department",
    responses=UNAUTHORIZED,
)
def employee_stats(_user: Reader, db: DbSession) -> EmployeeStats:
    return employee_service.get_stats(db)


@router.get(
    "/{employee_id}",
    response_model=EmployeeReadSensitive | EmployeeRead,
    summary="Get one employee",
    responses=UNAUTHORIZED | NOT_FOUND,
)
def get_employee(
    employee_id: uuid.UUID, user: Reader, db: DbSession
) -> EmployeeRead | EmployeeReadSensitive:
    return _present(user, employee_service.get_employee(db, employee_id))


@router.post(
    "",
    response_model=EmployeeReadSensitive,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee (Admin, Super Admin)",
    responses=UNAUTHORIZED | FORBIDDEN | CONFLICT,
)
def create_employee(
    request: EmployeeCreate, actor: Writer, db: DbSession
) -> EmployeeReadSensitive:
    return EmployeeReadSensitive.model_validate(
        employee_service.create_employee(db, actor, request)
    )


@router.patch(
    "/{employee_id}",
    response_model=EmployeeReadSensitive,
    summary="Update an employee (Admin, Super Admin)",
    responses=UNAUTHORIZED | FORBIDDEN | NOT_FOUND | CONFLICT,
)
def update_employee(
    employee_id: uuid.UUID, request: EmployeeUpdate, actor: Writer, db: DbSession
) -> EmployeeReadSensitive:
    return EmployeeReadSensitive.model_validate(
        employee_service.update_employee(db, actor, employee_id, request)
    )


@router.delete(
    "/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete an employee (Super Admin: any; Admin: only records they created)",
    responses=UNAUTHORIZED | FORBIDDEN | NOT_FOUND,
)
def delete_employee(employee_id: uuid.UUID, actor: Deleter, db: DbSession) -> None:
    employee_service.delete_employee(db, actor, employee_id)
