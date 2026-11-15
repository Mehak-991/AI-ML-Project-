import uuid
from collections.abc import Sequence
from typing import Literal

from sqlalchemy import Select, func, or_, select, update

from app.database.models.employee import Employee
from app.repositories.base import BaseRepository

SortField = Literal["last_name", "hire_date", "created_at", "department", "employee_code"]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class EmployeeRepository(BaseRepository[Employee]):
    model = Employee

    def get_by_code(self, code: str) -> Employee | None:
        return self.session.scalars(
            select(Employee).where(Employee.employee_code == code)
        ).first()

    def get_by_email(self, email: str) -> Employee | None:
        return self.session.scalars(
            select(Employee).where(func.lower(Employee.email) == email.lower())
        ).first()

    def _filtered(
        self,
        *,
        search: str | None,
        department: str | None,
        status: str | None,
        manager_id: uuid.UUID | None,
    ) -> Select:
        stmt = select(Employee)
        if search:
            term = f"%{_escape_like(search.lower().strip())}%"
            stmt = stmt.where(
                or_(
                    func.lower(Employee.first_name).like(term, escape="\\"),
                    func.lower(Employee.last_name).like(term, escape="\\"),
                    func.lower(Employee.email).like(term, escape="\\"),
                    func.lower(Employee.employee_code).like(term, escape="\\"),
                    func.lower(Employee.job_title).like(term, escape="\\"),
                )
            )
        if department:
            stmt = stmt.where(func.lower(Employee.department) == department.lower().strip())
        if status:
            stmt = stmt.where(Employee.employment_status == status)
        if manager_id:
            stmt = stmt.where(Employee.manager_id == manager_id)
        return stmt

    def list_filtered(
        self,
        *,
        search: str | None = None,
        department: str | None = None,
        status: str | None = None,
        manager_id: uuid.UUID | None = None,
        sort: SortField = "last_name",
        descending: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[Employee], int]:
        stmt = self._filtered(
            search=search, department=department, status=status, manager_id=manager_id
        )
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        column = getattr(Employee, sort)
        order = column.desc() if descending else column.asc()
        items = self.session.scalars(
            stmt.order_by(order, Employee.id).offset(offset).limit(limit)
        ).all()
        return items, total

    def clear_manager(self, manager_id: uuid.UUID) -> None:
        """Detach direct reports (explicit, so it also works where FKs are not enforced)."""
        self.session.execute(
            update(Employee).where(Employee.manager_id == manager_id).values(manager_id=None)
        )

    def counts_by(self, column_name: str) -> dict[str, int]:
        column = getattr(Employee, column_name)
        rows = self.session.execute(select(column, func.count()).group_by(column)).all()
        return {str(key): int(count) for key, count in rows}
