"""add datasets.owner_id for object-level authorization

Additive only: existing rows keep owner_id NULL (legacy, visible to every authenticated user).

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("datasets") as batch:
        batch.add_column(sa.Column("owner_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_datasets_owner_id_users", "users", ["owner_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_datasets_owner_id", ["owner_id"])


def downgrade() -> None:
    with op.batch_alter_table("datasets") as batch:
        batch.drop_index("ix_datasets_owner_id")
        batch.drop_constraint("fk_datasets_owner_id_users", type_="foreignkey")
        batch.drop_column("owner_id")
