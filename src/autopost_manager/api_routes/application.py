from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from autopost_manager import api as handlers
from autopost_manager.api_routes import api_router
from autopost_manager.config import get_settings


def create_application() -> FastAPI:
    application = FastAPI(title="Autopost Manager", lifespan=handlers.lifespan)
    application.middleware("http")(handlers.alert_unhandled_errors)
    application.middleware("http")(handlers.security_headers)
    application.include_router(api_router())

    miniapp_dir = get_settings().miniapp_dir
    if miniapp_dir.exists():
        application.mount("/miniapp", StaticFiles(directory=miniapp_dir, html=True), name="miniapp")

    return application
