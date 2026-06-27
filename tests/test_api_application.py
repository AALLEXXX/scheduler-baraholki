from __future__ import annotations

from fastapi.staticfiles import StaticFiles

from autopost_manager.api.application import create_application
from autopost_manager.config import get_settings


def test_create_application_uses_explicit_settings_for_static_mount(tmp_path) -> None:
    miniapp_dir = tmp_path / "miniapp"
    miniapp_dir.mkdir()
    settings = get_settings().model_copy(update={"miniapp_dir": miniapp_dir})

    app = create_application(settings)

    miniapp_route = next(route for route in app.routes if getattr(route, "path", None) == "/miniapp")
    assert isinstance(miniapp_route.app, StaticFiles)
