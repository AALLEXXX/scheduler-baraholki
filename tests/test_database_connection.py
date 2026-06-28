from __future__ import annotations

from sqlalchemy import text

from autopost_manager.database import DatabaseProvider, create_database_provider


def test_create_database_provider_builds_isolated_session_factory() -> None:
    provider = create_database_provider("sqlite+pysqlite:///:memory:")

    assert isinstance(provider, DatabaseProvider)
    with provider.session_factory() as session:
        assert session.execute(text("select 1")).scalar_one() == 1
