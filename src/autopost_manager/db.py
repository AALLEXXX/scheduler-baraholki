from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from autopost_manager.config import get_settings
from autopost_manager.database.connection import Base
from autopost_manager.database.connection import SessionLocal
from autopost_manager.database.connection import engine
from autopost_manager.database.connection import get_db


def create_schema() -> None:
    from autopost_manager import models  # noqa: F401

    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(bind=engine)
        return

    run_migrations()


def alembic_config() -> Config:
    root = Path(__file__).resolve().parents[2]
    candidates = [Path.cwd() / "alembic.ini", root / "alembic.ini"]
    config_path = next((path for path in candidates if path.exists()), candidates[-1])
    config = Config(str(config_path))
    config.set_main_option("script_location", str(config_path.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
    return config


def run_migrations() -> None:
    command.upgrade(alembic_config(), "head")


__all__ = [
    "Base",
    "SessionLocal",
    "alembic_config",
    "create_schema",
    "engine",
    "get_db",
    "run_migrations",
]
