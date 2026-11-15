"""Employee records managed by Admins and Super Admins, readable by every role."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin

EMPLOYMENT_STATUSES = ("active", "on_leave", "terminated")


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "employment_status IN ('active', 'on_leave', 'terminated')",
            name="employment_status_valid",
        ),
        CheckConstraint("salary IS NULL OR salary >= 0", name="salary_non_negative"),
        CheckConstraint("manager_id IS NULL OR manager_id <> id", name="not_own_manager"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    # Stored lower-cased by the service so uniqueness is case-insensitive.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    department: Mapped[str] = mapped_column(String(100), index=True)
    job_title: Mapped[str] = mapped_column(String(150))
    employment_status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active", index=True
    )
    hire_date: Mapped[date] = mapped_column(Date)

    # Sensitive: only returned to roles holding employees:read_sensitive.
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
