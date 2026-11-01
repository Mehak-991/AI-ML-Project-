"""add partial index on jobs(status, created_at) for worker polling

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-01

Eliminates full-table-scan on jobs during worker polling and stalled-job recovery.

  claim_next_queued_job: WHERE status IN ('queued','retry_pending') ORDER BY created_at
  reap_stalled_jobs:     WHERE status = 'running' ORDER BY created_at

Without an index both queries do sequential scans over all historical
completed/failed/cancelled rows as the table grows. The partial index covers
only active statuses, keeping it small and the worker poll sub-millisecond
even at 100k+ rows. No data is changed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index(
            "ix_jobs_status_created_at",
            "jobs",
            ["status", "created_at"],
            postgresql_where=sa.text("status IN ('queued', 'running', 'retry_pending')"),
        )
    else:
        # SQLite does not support partial indexes; create a full index for tests.
        op.create_index(
            "ix_jobs_status_created_at",
            "jobs",
            ["status", "created_at"],
        )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_created_at", table_name="jobs")
