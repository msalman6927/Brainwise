from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve the env file from this file, not the CWD, so the app boots the same
# whether uvicorn is started from the repo root or from backend/.
BACKEND_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = BACKEND_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE)

    app_name: str = "Brainwise"

    database_url: str

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"

    jwt_secret: str | None = None
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 7

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
