from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from autopost_manager import api_runtime
from autopost_manager.api.rest import rest_router
from autopost_manager.api.rpc import rpc_router
from autopost_manager.config import Settings, get_settings


def api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(rest_router())
    router.include_router(rpc_router())
    return router


def create_application(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    application = FastAPI(title="Autopost Manager", lifespan=api_runtime.lifespan)
    application.middleware("http")(api_runtime.alert_unhandled_errors)
    application.middleware("http")(api_runtime.security_headers)
    application.include_router(api_router())

    miniapp_dir = resolved_settings.miniapp_dir
    if miniapp_dir.exists():
        application.mount("/miniapp", StaticFiles(directory=miniapp_dir, html=True), name="miniapp")

    return application
