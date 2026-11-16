"""drift_reports.results JSON -> JSONB on PostgreSQL (align schema with the ORM)

Revision ID: 0014_drift_results_jsonb
Revises: 0013_employees_audit
Create Date: 2026-11-16

Migration 0005 created drift_reports.results as JSON while the model declares JSONType
(JSONB on PostgreSQL). Fresh PostgreSQL databases therefore drifted from the ORM. This
converts the column only when it is still `json`, so it is a no-op on databases that already
use JSONB (e.g. those migrated by the old lineage) and on SQLite.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0014_drift_results_jsonb"
down_revision: str | Sequence[str] | None = "0013_employees_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _current_type(bind) -> str | None:
    return bind.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name = 'drift_reports' AND column_name = 'results' "
            "AND table_schema = current_schema()"
        )
    ).scalar()


def _alter(target: str) -> None:
    if context.is_offline_mode():
        # `alembic upgrade --sql` has no connection to inspect; emit the (idempotent)
        # conversion unconditionally. Casting jsonb -> jsonb is valid, just a table rewrite.
        if context.get_context().dialect.name != "postgresql":
            return
    else:
        bind = op.get_bind()
        if bind.dialect.name != "postgresql" or _current_type(bind) == target:
            return
    column = "ALTER TABLE drift_reports ALTER COLUMN results"
    op.execute(sa.text(f"{column} DROP DEFAULT"))
    op.execute(sa.text(f"{column} TYPE {target} USING results::{target}"))
    op.execute(sa.text(f"{column} SET DEFAULT '{{}}'::{target}"))


def upgrade() -> None:
    _alter("jsonb")


def downgrade() -> None:
    _alter("json")
