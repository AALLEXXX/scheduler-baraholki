from __future__ import annotations

from fastapi import APIRouter

from autopost_manager.api.rpc import account_login, post_actions, session_sync


def rpc_router() -> APIRouter:
    router = APIRouter()
    for module in (account_login, session_sync, post_actions):
        router.include_router(module.router)
    return router
