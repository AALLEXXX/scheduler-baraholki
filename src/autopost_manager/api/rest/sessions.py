from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import TelegramSessionOut

router = APIRouter()

add_dual_route(
    router,
    "/api/sessions",
    "/rest/autopost/sessions",
    handlers.list_sessions,
    methods=["GET"],
    response_model=list[TelegramSessionOut],
)
