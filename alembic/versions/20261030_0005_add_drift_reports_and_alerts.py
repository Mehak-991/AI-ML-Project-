"""add drift_reports and drift_alerts tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30

Adds:
- drift_reports table (model_id, report_type, overall_status, results, sample_size, summary)
- drift_alerts table (model_id, drift_report_id, alert_type, severity, feature_name,
  metric_name, metric_value, threshold, message, resolved)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. drift_reports
    op.create_table(
        "drift_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("report_type", sa.String(length=32), nullable=False),
        sa.Column("overall_status", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("results", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["ml_models.id"],
            name="fk_drift_reports_model_id_ml_models",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drift_reports"),
    )
    op.create_index("ix_drift_reports_model_id", "drift_reports", ["model_id"])
    op.create_index("ix_drift_reports_report_type", "drift_reports", ["report_type"])
    op.create_index("ix_drift_reports_overall_status", "drift_reports", ["overall_status"])

    # 2. drift_alerts
    op.create_table(
        "drift_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("drift_report_id", sa.Uuid(), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("feature_name", sa.String(length=255), nullable=True),
        sa.Column("metric_name", sa.String(length=64), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["ml_models.id"],
            name="fk_drift_alerts_model_id_ml_models",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["drift_report_id"],
            ["drift_reports.id"],
            name="fk_drift_alerts_drift_report_id_drift_reports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_drift_alerts"),
    )
    op.create_index("ix_drift_alerts_model_id", "drift_alerts", ["model_id"])
    op.create_index("ix_drift_alerts_drift_report_id", "drift_alerts", ["drift_report_id"])
    op.create_index("ix_drift_alerts_severity", "drift_alerts", ["severity"])
    op.create_index("ix_drift_alerts_resolved", "drift_alerts", ["resolved"])


def downgrade() -> None:
    op.drop_index("ix_drift_alerts_resolved", table_name="drift_alerts")
    op.drop_index("ix_drift_alerts_severity", table_name="drift_alerts")
    op.drop_index("ix_drift_alerts_drift_report_id", table_name="drift_alerts")
    op.drop_index("ix_drift_alerts_model_id", table_name="drift_alerts")
    op.drop_table("drift_alerts")

    op.drop_index("ix_drift_reports_overall_status", table_name="drift_reports")
    op.drop_index("ix_drift_reports_report_type", table_name="drift_reports")
    op.drop_index("ix_drift_reports_model_id", table_name="drift_reports")
    op.drop_table("drift_reports")
