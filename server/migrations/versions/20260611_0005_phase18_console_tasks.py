"""phase 18 console task ownership

Revision ID: 20260611_0005
Revises: 20260610_0004
Create Date: 2026-06-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260611_0005"
down_revision = "20260610_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generation_tasks", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.create_index("ix_generation_tasks_created_by_user_id", "generation_tasks", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_generation_tasks_created_by_user_id", table_name="generation_tasks")
    op.drop_column("generation_tasks", "created_by_user_id")
