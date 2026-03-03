from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always resolve .env relative to this file (backend/), regardless of cwd
_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8")

    ANTHROPIC_API_KEY: str
    DATABASE_URL: str
    SECRET_KEY: str = "change-me-in-production"


settings = Settings()
