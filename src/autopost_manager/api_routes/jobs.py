from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import JobOut

router = APIRouter()

router.add_api_route(
    "/api/jobs",
    handlers.list_jobs,
    methods=["GET"],
    response_model=list[JobOut],
)
