from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import DeletePostOut, PostOut

router = APIRouter()

router.add_api_route(
    "/api/posts",
    handlers.list_posts,
    methods=["GET"],
    response_model=list[PostOut],
)
router.add_api_route(
    "/api/posts",
    handlers.create_post,
    methods=["POST"],
    response_model=PostOut,
)
router.add_api_route(
    "/api/posts/{post_id}/schedule",
    handlers.schedule_post,
    methods=["POST"],
    response_model=PostOut,
)
router.add_api_route(
    "/api/posts/{post_id}/pause",
    handlers.pause_post,
    methods=["PATCH"],
    response_model=PostOut,
)
router.add_api_route(
    "/api/posts/{post_id}/resume",
    handlers.resume_post,
    methods=["PATCH"],
    response_model=PostOut,
)
router.add_api_route(
    "/api/posts/{post_id}",
    handlers.delete_post,
    methods=["DELETE"],
    response_model=DeletePostOut,
)
router.add_api_route(
    "/api/posts/{post_id}/enqueue-now",
    handlers.enqueue_now,
    methods=["POST"],
)
