"""Environment based settings for the SaaS backend."""

import os
from urllib.parse import urlparse

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
    admin_username = os.getenv("FREECADAI_ADMIN_USERNAME", "admin")
    admin_password = os.getenv("FREECADAI_ADMIN_PASSWORD", "")
    admin_session_hours = int(os.getenv("FREECADAI_ADMIN_SESSION_HOURS", "12"))
    user_session_hours = int(os.getenv("FREECADAI_USER_SESSION_HOURS", "168"))
    auto_migrate = os.getenv("FREECADAI_AUTO_MIGRATE", "1").lower() in {"1", "true", "yes", "on"}
    model_asset_storage_dir = os.getenv("FREECADAI_MODEL_ASSET_STORAGE_DIR", "server/app/static/model_assets")
    model_asset_max_upload_mb = int(os.getenv("FREECADAI_MODEL_ASSET_MAX_UPLOAD_MB", "100"))
    model_asset_upload_token_minutes = int(os.getenv("FREECADAI_MODEL_ASSET_UPLOAD_TOKEN_MINUTES", "30"))
    model_asset_allowed_extensions = os.getenv("FREECADAI_MODEL_ASSET_ALLOWED_EXTENSIONS", ".fcstd,.step,.stp,.stl,.obj").lower()

    @property
    def llm_provider(self) -> str:
        explicit = os.getenv("FREECADAI_LLM_PROVIDER", "").strip()
        if explicit:
            return explicit
        host = (urlparse(self.llm_base_url).hostname or "").lower()
        model = (self.llm_model or "").lower()
        if "deepseek" in host or "deepseek" in model:
            return "deepseek"
        if "openai" in host or model.startswith("gpt-"):
            return "openai"
        return "openai-compatible"


settings = Settings()
