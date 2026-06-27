from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import AuditMessageOut, AuditPageOut

router = APIRouter()

add_dual_route(
    router,
    "/api/audit",
    "/rest/autopost/audit",
    handlers.list_audit,
    methods=["GET"],
    response_model=AuditPageOut,
)
add_dual_route(
    router,
    "/api/audit/{job_id}/message",
    "/rest/autopost/audit/{job_id}/message",
    handlers.get_audit_message,
    methods=["GET"],
    response_model=AuditMessageOut,
)
