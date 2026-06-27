from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route

router = APIRouter()

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
