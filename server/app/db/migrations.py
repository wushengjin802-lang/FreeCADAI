"""Database migration helpers."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from server.app.db.session import engine


BUSINESS_TABLES = {
    "workspaces",
    "api_keys",
    "generation_tasks",
    "templates",
    "admin_users",
}


def alembic_config():
    server_dir = Path(__file__).resolve().parents[2]
    config = Config(str(server_dir / "alembic.ini"))
    config.set_main_option("script_location", str(server_dir / "migrations"))
    return config


def migrate_database():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    config = alembic_config()

    if "alembic_version" not in table_names and table_names.intersection(BUSINESS_TABLES):
        command.stamp(config, "head")
        return "stamped"

    command.upgrade(config, "head")
    return "upgraded"
