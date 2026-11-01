"""index prediction_logs for newest-first history pagination

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-31

History endpoints page newest-first (ORDER BY created_at DESC LIMIT n), optionally per
model. Measured on 200k rows (Phase 20 report): unfiltered history 97 ms -> 0.2 ms,
per-model history 22 ms -> 0.7 ms. Both indexes are scanned backward for DESC.

- add ix_prediction_logs_model_id_created_at (model_id, created_at)
- add ix_prediction_logs_created_at (created_at)
- drop ix_prediction_logs_model_id: the composite's leading column serves every lookup
  it served (including ON DELETE CASCADE from ml_models). Re-created on downgrade.

No data is changed. Plain CREATE INDEX briefly blocks writes to prediction_logs; on a
large table run the CREATE INDEX statements CONCURRENTLY by hand before upgrading.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_prediction_logs_model_id_created_at",
        "prediction_logs",
        ["model_id", "created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_prediction_logs_created_at", "prediction_logs", ["created_at"], if_not_exists=True
    )
    op.drop_index("ix_prediction_logs_model_id", table_name="prediction_logs")


def downgrade() -> None:
    op.create_index("ix_prediction_logs_model_id", "prediction_logs", ["model_id"], unique=False)
    op.drop_index("ix_prediction_logs_created_at", table_name="prediction_logs")
    op.drop_index("ix_prediction_logs_model_id_created_at", table_name="prediction_logs")
