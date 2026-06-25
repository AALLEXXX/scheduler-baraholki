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
    app_encryption_key: str | None = None
    allow_local_auth_bypass: bool = False
    local_dev_user_id: int = 0
    telegram_init_data_max_age_seconds: int = 21600

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
    max_sessions_per_user: int = 3
    max_targets_per_post: int = 15
    max_active_posts_per_user: int = 50
    max_jobs_per_user_per_day: int = 300
    max_media_items_per_post: int = 10
    max_bot_file_bytes: int = 25 * 1024 * 1024
    telegram_operation_timeout_seconds: int = 60

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
