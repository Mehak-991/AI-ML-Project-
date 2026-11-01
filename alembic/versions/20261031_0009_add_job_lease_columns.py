"""add worker lease columns to jobs for stalled-job recovery

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-31

Adds (additive, nullable; existing rows keep NULL):
- jobs.worker_id: identity of the process currently executing the job
- jobs.heartbeat_at: last liveness signal from that process
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.add_column(sa.Column("worker_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.drop_column("heartbeat_at")
        batch.drop_column("worker_id")
