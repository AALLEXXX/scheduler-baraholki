from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import AppConfigOut, UserSettingsOut

router = APIRouter()

add_dual_route(
    router,
    "/api/app-config",
    "/rest/autopost/app-config",
    handlers.app_config,
    methods=["GET"],
    response_model=AppConfigOut,
)
add_dual_route(
    router,
    "/api/user-settings",
    "/rest/autopost/user-settings",
    handlers.get_user_settings,
    methods=["GET"],
    response_model=UserSettingsOut,
)
