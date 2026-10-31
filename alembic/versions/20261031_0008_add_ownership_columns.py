"""add ownership columns for object-level authorization

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-31

Adds (additive, nullable; existing rows keep NULL):
- ml_models.owner_id -> users.id (ON DELETE SET NULL)
- prediction_logs.requested_by_id -> users.id (ON DELETE SET NULL)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ml_models") as batch:
        batch.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_ml_models_owner_id_users", "users", ["owner_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_ml_models_owner_id", ["owner_id"])

    with op.batch_alter_table("prediction_logs") as batch:
        batch.add_column(sa.Column("requested_by_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_prediction_logs_requested_by_id_users",
            "users",
            ["requested_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_prediction_logs_requested_by_id", ["requested_by_id"])


def downgrade() -> None:
    with op.batch_alter_table("prediction_logs") as batch:
        batch.drop_index("ix_prediction_logs_requested_by_id")
        batch.drop_constraint("fk_prediction_logs_requested_by_id_users", type_="foreignkey")
        batch.drop_column("requested_by_id")

    with op.batch_alter_table("ml_models") as batch:
        batch.drop_index("ix_ml_models_owner_id")
        batch.drop_constraint("fk_ml_models_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
