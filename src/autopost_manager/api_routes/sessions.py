from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import TelegramSessionOut

router = APIRouter()

router.add_api_route(
    "/api/sessions",
    handlers.list_sessions,
    methods=["GET"],
    response_model=list[TelegramSessionOut],
)
router.add_api_route(
    "/api/sessions/{session_id}/sync-chats",
    handlers.sync_session_chats,
    methods=["POST"],
)
