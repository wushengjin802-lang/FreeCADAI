"""phase 20 enterprise notifications

Revision ID: 20260611_0006
Revises: 20260611_0005
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_0006"
down_revision = "20260611_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, default=""),
        sa.Column("level", sa.String(length=32), nullable=False, default="info"),
        sa.Column("status", sa.String(length=32), nullable=False, default="unread"),
        sa.Column("metadata_json", sa.JSON(), nullable=False, default=dict),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_workspace_id", "notifications", ["workspace_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])


def downgrade():
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_workspace_id", table_name="notifications")
    op.drop_table("notifications")
