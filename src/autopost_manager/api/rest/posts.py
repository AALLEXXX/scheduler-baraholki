from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import DeletePostOut, PostOut

router = APIRouter()

add_dual_route(
    router,
    "/api/posts",
    "/rest/autopost/posts",
    handlers.list_posts,
    methods=["GET"],
    response_model=list[PostOut],
)
add_dual_route(
    router,
    "/api/posts",
    "/rest/autopost/posts",
    handlers.create_post,
    methods=["POST"],
    response_model=PostOut,
)
add_dual_route(
    router,
    "/api/posts/{post_id}",
    "/rest/autopost/posts/{post_id}",
    handlers.delete_post,
    methods=["DELETE"],
    response_model=DeletePostOut,
)
