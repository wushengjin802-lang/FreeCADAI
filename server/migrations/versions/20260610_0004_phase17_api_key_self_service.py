"""phase 17 api key self service fields

Revision ID: 20260610_0004
Revises: 20260610_0003
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260610_0004"
down_revision = "20260610_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("api_keys", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column("api_keys", sa.Column("scopes_json", sa.JSON(), nullable=True))
    op.create_index("ix_api_keys_created_by_user_id", "api_keys", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_api_keys_created_by_user_id", table_name="api_keys")
    op.drop_column("api_keys", "scopes_json")
    op.drop_column("api_keys", "expires_at")
    op.drop_column("api_keys", "created_by_user_id")
