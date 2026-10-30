"""add experiments and experiment_runs tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-30

Adds:
- experiments table
- experiment_runs table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")

    op.create_table(
        "experiments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("target_column", sa.String(length=255), nullable=False),
        sa.Column("problem_type", sa.String(length=50), nullable=False),
        sa.Column("algorithm", sa.String(length=50), nullable=False),
        sa.Column("selected_features", json_type, nullable=True),
        sa.Column("hyperparameter_config", json_type, nullable=False),
        sa.Column("search_strategy", sa.String(length=50), nullable=False, server_default="none"),
        sa.Column("cv_folds", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("scoring_metric", sa.String(length=50), nullable=True),
        sa.Column("test_size", sa.Float(), nullable=False, server_default="0.2"),
        sa.Column("validation_size", sa.Float(), nullable=False, server_default="0.1"),
        sa.Column("random_state", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("dataset_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiments_name", "experiments", ["name"], unique=False)
    op.create_index("ix_experiments_dataset_id", "experiments", ["dataset_id"], unique=False)
    op.create_index("ix_experiments_status", "experiments", ["status"], unique=False)
    op.create_index("ix_experiments_created_by_id", "experiments", ["created_by_id"], unique=False)

    op.create_table(
        "experiment_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("experiment_id", sa.Uuid(), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("best_hyperparameters", json_type, nullable=True),
        sa.Column("validation_metrics", json_type, nullable=True),
        sa.Column("test_metrics", json_type, nullable=True),
        sa.Column("cv_results", json_type, nullable=True),
        sa.Column("registered_model_id", sa.Uuid(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_duration_seconds", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["registered_model_id"], ["ml_models.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_runs_experiment_id", "experiment_runs", ["experiment_id"], unique=False)
    op.create_index("ix_experiment_runs_status", "experiment_runs", ["status"], unique=False)
    op.create_index("ix_experiment_runs_registered_model_id", "experiment_runs", ["registered_model_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_experiment_runs_registered_model_id", table_name="experiment_runs")
    op.drop_index("ix_experiment_runs_status", table_name="experiment_runs")
    op.drop_index("ix_experiment_runs_experiment_id", table_name="experiment_runs")
    op.drop_table("experiment_runs")

    op.drop_index("ix_experiments_created_by_id", table_name="experiments")
    op.drop_index("ix_experiments_status", table_name="experiments")
    op.drop_index("ix_experiments_dataset_id", table_name="experiments")
    op.drop_index("ix_experiments_name", table_name="experiments")
    op.drop_table("experiments")
