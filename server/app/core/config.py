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


settings = Settings()
