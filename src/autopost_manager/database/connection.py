from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from autopost_manager.config import get_settings


class Base(DeclarativeBase):
    pass


@dataclass(frozen=True, slots=True)
class DatabaseProvider:
    engine: Engine
    session_factory: sessionmaker[Session]


def create_database_provider(database_url: str | None = None) -> DatabaseProvider:
    provider_engine = create_engine(database_url or get_settings().database_url, pool_pre_ping=True)
    return DatabaseProvider(
        engine=provider_engine,
        session_factory=sessionmaker(bind=provider_engine, expire_on_commit=False),
    )


default_provider = create_database_provider()
engine = default_provider.engine
SessionLocal = default_provider.session_factory


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
