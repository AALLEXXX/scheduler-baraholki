from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route

router = APIRouter()

router.add_api_route("/health", handlers.health, methods=["GET"])
add_dual_route(router, "/api/health", "/rest/autopost/health", handlers.api_health, methods=["GET"])
