"""employees, audit_logs and system_settings tables

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-15

Purely additive: three new tables, no existing data is touched.
- employees: employee records (sensitive columns: phone, salary)
- audit_logs: append-only trail of security-relevant and data-changing operations
- system_settings: whitelisted runtime settings managed by super admins
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_code", sa.String(length=32), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=False),
        sa.Column("job_title", sa.String(length=150), nullable=False),
        sa.Column(
            "employment_status", sa.String(length=16), nullable=False, server_default="active"
        ),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("salary", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("manager_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "employment_status IN ('active', 'on_leave', 'terminated')",
            name=op.f("ck_employees_employment_status_valid"),
        ),
        sa.CheckConstraint(
            "salary IS NULL OR salary >= 0", name=op.f("ck_employees_salary_non_negative")
        ),
        sa.CheckConstraint(
            "manager_id IS NULL OR manager_id <> id", name=op.f("ck_employees_not_own_manager")
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["employees.id"],
            name=op.f("fk_employees_manager_id_employees"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_employees_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_employees_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
    )
    op.create_index(op.f("ix_employees_employee_code"), "employees", ["employee_code"], unique=True)
    op.create_index(op.f("ix_employees_email"), "employees", ["email"], unique=True)
    op.create_index(op.f("ix_employees_department"), "employees", ["department"])
    op.create_index(op.f("ix_employees_employment_status"), "employees", ["employment_status"])
    op.create_index(op.f("ix_employees_manager_id"), "employees", ["manager_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("details", JSONType, nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index(op.f("ix_audit_logs_actor_id"), "audit_logs", ["actor_id"])
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"])
    op.create_index(
        "ix_audit_logs_category_created_at", "audit_logs", ["category", "created_at"]
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", JSONType, nullable=False),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name=op.f("fk_system_settings_updated_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_system_settings")),
    )


def downgrade() -> None:
    op.drop_table("system_settings")

    op.drop_index("ix_audit_logs_category_created_at", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_employees_manager_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_employment_status"), table_name="employees")
    op.drop_index(op.f("ix_employees_department"), table_name="employees")
    op.drop_index(op.f("ix_employees_email"), table_name="employees")
    op.drop_index(op.f("ix_employees_employee_code"), table_name="employees")
    op.drop_table("employees")
