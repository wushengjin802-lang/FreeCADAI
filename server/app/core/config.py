"""Environment based settings for the SaaS backend."""

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency installed in server env.
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


class Settings:
    app_name = "FreeCADAI SaaS"
    database_url = os.getenv(
        "FREECADAI_DATABASE_URL",
        "mysql+pymysql://freecadai:freecadai_password@127.0.0.1:3306/freecadai?charset=utf8mb4",
    )
    plugin_api_key = os.getenv("FREECADAI_PLUGIN_API_KEY", "")
    llm_base_url = os.getenv("FREECADAI_LLM_BASE_URL", "https://api.openai.com/v1")
    llm_api_key = os.getenv("FREECADAI_LLM_API_KEY", "")
    llm_model = os.getenv("FREECADAI_LLM_MODEL", "gpt-4.1-mini")
    llm_temperature = float(os.getenv("FREECADAI_LLM_TEMPERATURE", "0.1"))
    redis_url = os.getenv("FREECADAI_REDIS_URL", "redis://127.0.0.1:6379/0")
    admin_token = os.getenv("FREECADAI_ADMIN_TOKEN", "")
    admin_username = os.getenv("FREECADAI_ADMIN_USERNAME", "admin")
    admin_password = os.getenv("FREECADAI_ADMIN_PASSWORD", admin_token)
    admin_session_hours = int(os.getenv("FREECADAI_ADMIN_SESSION_HOURS", "12"))
    auto_migrate = os.getenv("FREECADAI_AUTO_MIGRATE", "1").lower() in {"1", "true", "yes", "on"}


settings = Settings()
