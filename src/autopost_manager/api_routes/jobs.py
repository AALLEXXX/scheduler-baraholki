from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api_routes.helpers import add_dual_route
from autopost_manager.schemas import JobOut

router = APIRouter()

add_dual_route(
    router,
    "/api/jobs",
    "/rest/autopost/jobs",
    handlers.list_jobs,
    methods=["GET"],
    response_model=list[JobOut],
)
