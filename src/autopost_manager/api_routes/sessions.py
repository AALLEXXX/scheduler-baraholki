from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api_routes.helpers import add_dual_route
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
add_dual_route(
    router,
    "/api/sessions/{session_id}/sync-chats",
    (
        "/rpc/autopost/sync-target-chats/{session_id}",
        "/rpc/autopost/sessions/{session_id}/sync-chats",
    ),
    handlers.sync_session_chats,
    methods=["POST"],
)
