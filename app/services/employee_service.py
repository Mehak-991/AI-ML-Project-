"""Employee business rules. Route-level permissions decide *who* may call these; this
module enforces *what* is valid (uniqueness, manager hierarchy, required fields) and
records every change in the audit log within the same transaction."""

import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictError,
    DataValidationError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.permissions import Permission, has_permission
from app.database.models.employee import Employee
from app.database.models.user import User
from app.repositories.employees import EmployeeRepository
from app.schemas.employees import EmployeeCreate, EmployeeStats, EmployeeUpdate
from app.services import audit_service

# Never written to audit details by value (only "changed").
SENSITIVE_FIELDS = frozenset({"phone", "salary"})
REQUIRED_FIELDS = frozenset(
    {
        "first_name",
        "last_name",
        "email",
        "department",
        "job_title",
        "employment_status",
        "hire_date",
    }
)
MAX_MANAGER_CHAIN = 100


def get_employee(session: Session, employee_id: uuid.UUID) -> Employee:
    employee = EmployeeRepository(session).get(employee_id)
    if employee is None:
        raise NotFoundError(f"Employee {employee_id} not found.")
    return employee


def _ensure_unique(
    repo: EmployeeRepository, *, code: str | None, email: str | None, exclude: uuid.UUID | None
) -> None:
    if code is not None:
        existing = repo.get_by_code(code)
        if existing is not None and existing.id != exclude:
            raise ConflictError(f"Employee code '{code}' is already in use.")
    if email is not None:
        existing = repo.get_by_email(email)
        if existing is not None and existing.id != exclude:
            raise ConflictError(f"An employee with email '{email}' already exists.")


def _validate_manager(
    repo: EmployeeRepository, employee_id: uuid.UUID | None, manager_id: uuid.UUID | None
) -> None:
    if manager_id is None:
        return
    if manager_id == employee_id:
        raise DataValidationError("An employee cannot be their own manager.")
    manager = repo.get(manager_id)
    if manager is None:
        raise DataValidationError(f"Manager {manager_id} does not exist.")
    # Walk up the chain: assigning a manager must not create a reporting cycle.
    seen: set[uuid.UUID] = set()
    current = manager
    for _ in range(MAX_MANAGER_CHAIN):
        if current.manager_id is None:
            return
        if current.manager_id == employee_id or current.manager_id in seen:
            raise DataValidationError("This manager assignment would create a reporting cycle.")
        seen.add(current.manager_id)
        parent = repo.get(current.manager_id)
        if parent is None:
            return
        current = parent
    raise DataValidationError("The management chain is too deep.")


def _commit(session: Session) -> None:
    """Commit, turning a lost race on a unique constraint into a clean 409."""
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "The employee conflicts with an existing record (code or email already in use)."
        ) from exc


def create_employee(session: Session, actor: User, data: EmployeeCreate) -> Employee:
    repo = EmployeeRepository(session)
    email = str(data.email).lower()
    _ensure_unique(repo, code=data.employee_code, email=email, exclude=None)
    employee_id = uuid.uuid4()
    _validate_manager(repo, employee_id, data.manager_id)

    employee = Employee(
        id=employee_id,
        **data.model_dump(exclude={"email"}),
        email=email,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    repo.add(employee)
    audit_service.record(
        session,
        actor=actor,
        action="employee.create",
        category="employee",
        target_type="employee",
        target_id=employee.id,
        details={"employee_code": employee.employee_code, "email": email},
    )
    _commit(session)
    session.refresh(employee)
    return employee


def update_employee(
    session: Session, actor: User, employee_id: uuid.UUID, data: EmployeeUpdate
) -> Employee:
    repo = EmployeeRepository(session)
    employee = get_employee(session, employee_id)
    # Only fields the client actually sent; an explicit null clears optional fields.
    patch: dict[str, Any] = {k: getattr(data, k) for k in data.model_fields_set}
    nulled = sorted(k for k, v in patch.items() if v is None and k in REQUIRED_FIELDS)
    if nulled:
        raise DataValidationError("Required fields cannot be cleared.", details={"fields": nulled})
    if "email" in patch:
        patch["email"] = str(patch["email"]).lower()
        _ensure_unique(repo, code=None, email=patch["email"], exclude=employee.id)
    if "manager_id" in patch:
        _validate_manager(repo, employee.id, patch["manager_id"])

    changes: dict[str, Any] = {}
    for field, value in patch.items():
        old = getattr(employee, field)
        if old == value:
            continue
        setattr(employee, field, value)
        changes[field] = (
            "changed" if field in SENSITIVE_FIELDS else {"old": _plain(old), "new": _plain(value)}
        )
    if not changes:
        return employee

    employee.updated_by_id = actor.id
    audit_service.record(
        session,
        actor=actor,
        action="employee.update",
        category="employee",
        target_type="employee",
        target_id=employee.id,
        details={"employee_code": employee.employee_code, "changes": changes},
    )
    _commit(session)
    session.refresh(employee)
    return employee


def can_delete(actor: User, employee: Employee) -> bool:
    """Super admins delete any record; admins only records they created themselves."""
    if has_permission(actor.role, Permission.EMPLOYEES_DELETE):
        return True
    return (
        has_permission(actor.role, Permission.EMPLOYEES_DELETE_OWN)
        and employee.created_by_id is not None
        and employee.created_by_id == actor.id
    )


def delete_employee(session: Session, actor: User, employee_id: uuid.UUID) -> None:
    repo = EmployeeRepository(session)
    employee = get_employee(session, employee_id)
    if not can_delete(actor, employee):
        raise PermissionDeniedError(
            "Access forbidden: admins can delete only the employee records they created."
        )
    repo.clear_manager(employee.id)
    audit_service.record(
        session,
        actor=actor,
        action="employee.delete",
        category="employee",
        target_type="employee",
        target_id=employee.id,
        details={
            "employee_code": employee.employee_code,
            "email": employee.email,
            "own_record": employee.created_by_id == actor.id,
        },
    )
    session.delete(employee)
    session.commit()


def get_stats(session: Session) -> EmployeeStats:
    repo = EmployeeRepository(session)
    by_status = repo.counts_by("employment_status")
    return EmployeeStats(
        total=sum(by_status.values()),
        by_status=by_status,
        by_department=repo.counts_by("department"),
    )


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
