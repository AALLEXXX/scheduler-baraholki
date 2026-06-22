from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from autopost_manager.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def create_schema() -> None:
    from autopost_manager import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_runtime_columns()


def ensure_runtime_columns() -> None:
    if engine.dialect.name != "postgresql":
        return

    statements = [
        "ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'credentials_needed'",
        "ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'code_needed'",
        "ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'password_needed'",
        "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS owner_telegram_id BIGINT",
        "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS api_id INTEGER",
        "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS api_hash VARCHAR(160)",
        "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS phone_code_hash VARCHAR(300)",
        "ALTER TABLE target_chats ADD COLUMN IF NOT EXISTS owner_telegram_id BIGINT",
        "ALTER TABLE target_chats ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT true",
        "CREATE INDEX IF NOT EXISTS ix_telegram_sessions_owner_telegram_id ON telegram_sessions (owner_telegram_id)",
        "CREATE INDEX IF NOT EXISTS ix_target_chats_owner_telegram_id ON target_chats (owner_telegram_id)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
