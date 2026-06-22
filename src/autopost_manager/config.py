from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    app_base_url: str = "http://localhost:8000"
    mini_app_url: str = "http://localhost:8000/miniapp/"
    miniapp_dir: Path = Path("/app/miniapp")
    app_secret: str = Field(min_length=16)

    bot_token: str = Field(min_length=20)
    bot_username: str = "scheduler_baraholki_bot"
    admin_telegram_ids: str = ""

    telegram_api_id: int
    telegram_api_hash: str = Field(min_length=16)
    telegram_sessions_dir: Path = Path("/data/sessions")

    database_url: str = "postgresql+psycopg://autopost:autopost@postgres:5432/autopost"
    scheduler_tick_seconds: int = 15
    worker_tick_seconds: int = 5
    default_min_send_interval_seconds: int = 30

    @property
    def admin_ids(self) -> set[int]:
        return {
            int(value.strip())
            for value in self.admin_telegram_ids.split(",")
            if value.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
