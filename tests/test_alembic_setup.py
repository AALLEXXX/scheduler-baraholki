from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_alembic_configuration_is_present() -> None:
    assert (ROOT / "alembic.ini").is_file()
    assert (ROOT / "alembic" / "env.py").is_file()
    assert any((ROOT / "alembic" / "versions").glob("*.py"))


def test_project_depends_on_alembic() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"alembic>=' in pyproject


def test_db_upgrade_entrypoint_uses_database_migrations_module() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'autopost-db-upgrade = "autopost_manager.database.migrations:run_migrations"' in pyproject
    assert 'autopost-db-upgrade = "autopost_manager.db:run_migrations"' not in pyproject
