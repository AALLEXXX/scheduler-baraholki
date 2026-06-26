from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import DialogFolderOut, TargetChatOut

router = APIRouter()

router.add_api_route(
    "/api/chats",
    handlers.list_chats,
    methods=["GET"],
    response_model=list[TargetChatOut],
)
router.add_api_route(
    "/api/folders",
    handlers.list_folders,
    methods=["GET"],
    response_model=list[DialogFolderOut],
)
router.add_api_route(
    "/api/chats",
    handlers.create_chat,
    methods=["POST"],
    response_model=TargetChatOut,
)
