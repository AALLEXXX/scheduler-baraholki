from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import AuditMessageOut, AuditPageOut

router = APIRouter()

router.add_api_route(
    "/api/audit",
    handlers.list_audit,
    methods=["GET"],
    response_model=AuditPageOut,
)
router.add_api_route(
    "/api/audit/{job_id}/message",
    handlers.get_audit_message,
    methods=["GET"],
    response_model=AuditMessageOut,
)
