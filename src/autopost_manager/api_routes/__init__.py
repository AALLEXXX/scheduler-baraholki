from __future__ import annotations

from fastapi import APIRouter

from autopost_manager.api_routes import account, admin, audit, chats, config, health, jobs, posts, sessions


def api_router() -> APIRouter:
    router = APIRouter()
    for module in (health, config, account, sessions, chats, posts, jobs, audit, admin):
        router.include_router(module.router)
    return router
