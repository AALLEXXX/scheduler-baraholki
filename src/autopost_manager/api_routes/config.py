from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import AppConfigOut, UserSettingsOut

router = APIRouter()

router.add_api_route(
    "/api/app-config",
    handlers.app_config,
    methods=["GET"],
    response_model=AppConfigOut,
)
router.add_api_route(
    "/api/user-settings",
    handlers.get_user_settings,
    methods=["GET"],
    response_model=UserSettingsOut,
)
