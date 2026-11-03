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
    op.add_column("datasets", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_datasets_owner_id"), "datasets", ["owner_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_datasets_owner_id_users"),
        "datasets",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_datasets_owner_id_users"), "datasets", type_="foreignkey")
    op.drop_index(op.f("ix_datasets_owner_id"), table_name="datasets")
    op.drop_column("datasets", "owner_id")
