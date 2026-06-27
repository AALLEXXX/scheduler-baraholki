from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import DialogFolderOut, TargetChatOut

router = APIRouter()

add_dual_route(
    router,
    "/api/chats",
    "/rest/autopost/chats",
    handlers.list_chats,
    methods=["GET"],
    response_model=list[TargetChatOut],
)
add_dual_route(
    router,
    "/api/folders",
    "/rest/autopost/folders",
    handlers.list_folders,
    methods=["GET"],
    response_model=list[DialogFolderOut],
)
add_dual_route(
    router,
    "/api/chats",
    "/rest/autopost/chats",
    handlers.create_chat,
    methods=["POST"],
    response_model=TargetChatOut,
)
