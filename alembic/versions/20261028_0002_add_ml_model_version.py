"""add per-name version to ml_models

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28

Existing rows are numbered 1, 2, 3... per model name in creation order, then a
UNIQUE (name, version) constraint is added.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ml_models") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), server_default="1", nullable=False))

    # Portable backfill (PostgreSQL and SQLite): rank rows sharing a name by creation time.
    op.execute(
        """
        UPDATE ml_models SET version = (
            SELECT COUNT(*) FROM ml_models AS earlier
            WHERE earlier.name = ml_models.name
              AND (earlier.created_at < ml_models.created_at
                   OR (earlier.created_at = ml_models.created_at AND earlier.id <= ml_models.id))
        )
        """
    )

    with op.batch_alter_table("ml_models") as batch:
        batch.create_unique_constraint("uq_ml_models_name_version", ["name", "version"])


def downgrade() -> None:
    with op.batch_alter_table("ml_models") as batch:
        batch.drop_constraint("uq_ml_models_name_version", type_="unique")
        batch.drop_column("version")
