from __future__ import annotations

from fastapi import APIRouter

from autopost_manager.api.rest import admin, audit, chats, config, health, jobs, posts, sessions


def rest_router() -> APIRouter:
    router = APIRouter()
    for module in (health, config, sessions, chats, posts, jobs, audit, admin):
        router.include_router(module.router)
    return router
