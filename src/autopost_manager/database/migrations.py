from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from autopost_manager.config import get_settings


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[3]
    candidates = [Path.cwd() / "alembic.ini", root / "alembic.ini"]
    config_path = next((path for path in candidates if path.exists()), candidates[-1])
    config = Config(str(config_path))
    config.set_main_option("script_location", str(config_path.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    return config


def run_migrations() -> None:
    command.upgrade(alembic_config(), "head")
