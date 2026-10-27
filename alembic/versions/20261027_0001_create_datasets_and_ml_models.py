"""create datasets and ml_models tables

Revision ID: 0001
Revises:
Create Date: 2026-10-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("n_rows", sa.Integer(), nullable=False),
        sa.Column("n_columns", sa.Integer(), nullable=False),
        sa.Column("columns", JSONType, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("stored_filename", name=op.f("uq_datasets_stored_filename")),
    )
    op.create_index(op.f("ix_datasets_sha256"), "datasets", ["sha256"], unique=False)

    op.create_table(
        "ml_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type", sa.String(length=32), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("feature_schema", JSONType, nullable=False),
        sa.Column("metrics", JSONType, nullable=False),
        sa.Column("training_metadata", JSONType, nullable=False),
        sa.Column("artifact_filename", sa.String(length=255), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("sklearn_version", sa.String(length=32), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_ml_models_dataset_id_datasets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_models")),
        sa.UniqueConstraint("artifact_filename", name=op.f("uq_ml_models_artifact_filename")),
    )
    op.create_index(op.f("ix_ml_models_dataset_id"), "ml_models", ["dataset_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_models_dataset_id"), table_name="ml_models")
    op.drop_table("ml_models")
    op.drop_index(op.f("ix_datasets_sha256"), table_name="datasets")
    op.drop_table("datasets")
