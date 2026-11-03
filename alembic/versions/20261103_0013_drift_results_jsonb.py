"""make drift_reports.results JSONB, matching the ORM model

Migration 0005 created it as JSON while the model declares JSONB, the only difference `alembic
check` reports. The cast keeps every value. PostgreSQL only: SQLite has a single JSON type.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _alter(column_type: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE drift_reports ALTER COLUMN results DROP DEFAULT")
    op.execute(
        f"ALTER TABLE drift_reports ALTER COLUMN results TYPE {column_type} "
        f"USING results::{column_type}"
    )
    op.execute(
        f"ALTER TABLE drift_reports ALTER COLUMN results SET DEFAULT '{{}}'::{column_type}"
    )


def upgrade() -> None:
    _alter("jsonb")


def downgrade() -> None:
    _alter("json")
