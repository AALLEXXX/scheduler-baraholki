from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import PostOut

router = APIRouter()

add_dual_route(
    router,
    "/api/posts/{post_id}/schedule",
    ("/rpc/autopost/schedule-post/{post_id}", "/rpc/autopost/posts/{post_id}/schedule"),
    handlers.schedule_post,
    methods=["POST"],
    response_model=PostOut,
)
add_dual_route(
    router,
    "/api/posts/{post_id}/pause",
    ("/rpc/autopost/pause-post/{post_id}", "/rpc/autopost/posts/{post_id}/pause"),
    handlers.pause_post,
    methods=["PATCH"],
    response_model=PostOut,
)
add_dual_route(
    router,
    "/api/posts/{post_id}/resume",
    ("/rpc/autopost/resume-post/{post_id}", "/rpc/autopost/posts/{post_id}/resume"),
    handlers.resume_post,
    methods=["PATCH"],
    response_model=PostOut,
)
add_dual_route(
    router,
    "/api/posts/{post_id}/enqueue-now",
    ("/rpc/autopost/enqueue-post-now/{post_id}", "/rpc/autopost/posts/{post_id}/enqueue-now"),
    handlers.enqueue_now,
    methods=["POST"],
)
