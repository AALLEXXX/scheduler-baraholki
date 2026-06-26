from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers

router = APIRouter()

router.add_api_route("/health", handlers.health, methods=["GET"])
router.add_api_route("/api/health", handlers.api_health, methods=["GET"])
