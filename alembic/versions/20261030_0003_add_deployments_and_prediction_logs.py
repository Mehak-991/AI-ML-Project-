"""add deployments and prediction_logs tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30

Adds:
- deployments table (model deployment lifecycle tracking)
- prediction_logs table (prediction audit logging, execution telemetry, and ground truth foundation)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.database.types import JSONType

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. deployments table
    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="Ready"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("environment", sa.String(length=64), nullable=False, server_default="production"),
        sa.Column("endpoint_url", sa.String(length=255), nullable=False),
        sa.Column("configuration", JSONType, nullable=False),
        sa.Column("deployed_at", sa.String(length=64), nullable=True),
        sa.Column("undeployed_at", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["ml_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deployments_model_id"), "deployments", ["model_id"], unique=False)
    op.create_index(op.f("ix_deployments_status"), "deployments", ["status"], unique=False)

    # 2. prediction_logs table
    op.create_table(
        "prediction_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("duration_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("problem_type", sa.String(length=32), nullable=False),
        sa.Column("error_category", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prediction_summary", JSONType, nullable=True),
        sa.Column("ground_truth", JSONType, nullable=True),
        sa.Column("is_evaluated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["ml_models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prediction_logs_model_id"), "prediction_logs", ["model_id"], unique=False)
    op.create_index(op.f("ix_prediction_logs_deployment_id"), "prediction_logs", ["deployment_id"], unique=False)
    op.create_index(op.f("ix_prediction_logs_status"), "prediction_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_prediction_logs_status"), table_name="prediction_logs")
    op.drop_index(op.f("ix_prediction_logs_deployment_id"), table_name="prediction_logs")
    op.drop_index(op.f("ix_prediction_logs_model_id"), table_name="prediction_logs")
    op.drop_table("prediction_logs")

    op.drop_index(op.f("ix_deployments_status"), table_name="deployments")
    op.drop_index(op.f("ix_deployments_model_id"), table_name="deployments")
    op.drop_table("deployments")
