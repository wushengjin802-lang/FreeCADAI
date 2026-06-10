"""phase 15 asset library

Revision ID: 20260610_0002
Revises: 20260608_0001
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa


revision = "20260610_0002"
down_revision = "20260608_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("generated_scripts", sa.Column("asset_id", sa.Integer(), nullable=True))
    op.add_column("generated_scripts", sa.Column("version_id", sa.Integer(), nullable=True))
    op.create_index("ix_generated_scripts_asset_id", "generated_scripts", ["asset_id"])

    op.create_table(
        "script_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("modeling_mode", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_script_assets_workspace_id", "script_assets", ["workspace_id"])
    op.create_index("ix_script_assets_task_id", "script_assets", ["task_id"])

    op.create_table(
        "script_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("script_assets.id"), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("script", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("expected_objects_json", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column("validation_error", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_script_versions_asset_id", "script_versions", ["asset_id"])
    op.create_index("ix_script_versions_task_id", "script_versions", ["task_id"])

    op.create_table(
        "model_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("script_asset_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.String(length=512), nullable=False),
        sa.Column("preview_uri", sa.String(length=512), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_model_assets_workspace_id", "model_assets", ["workspace_id"])
    op.create_index("ix_model_assets_script_asset_id", "model_assets", ["script_asset_id"])
    op.create_index("ix_model_assets_task_id", "model_assets", ["task_id"])


def downgrade():
    op.drop_index("ix_model_assets_task_id", table_name="model_assets")
    op.drop_index("ix_model_assets_script_asset_id", table_name="model_assets")
    op.drop_index("ix_model_assets_workspace_id", table_name="model_assets")
    op.drop_table("model_assets")
    op.drop_index("ix_script_versions_task_id", table_name="script_versions")
    op.drop_index("ix_script_versions_asset_id", table_name="script_versions")
    op.drop_table("script_versions")
    op.drop_index("ix_script_assets_task_id", table_name="script_assets")
    op.drop_index("ix_script_assets_workspace_id", table_name="script_assets")
    op.drop_table("script_assets")
    op.drop_index("ix_generated_scripts_asset_id", table_name="generated_scripts")
    op.drop_column("generated_scripts", "version_id")
    op.drop_column("generated_scripts", "asset_id")
