from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import AdminStatsOut, AdminUserOut, AdminUserPageOut, AuditMessageOut, AuditPageOut

router = APIRouter()

router.add_api_route(
    "/api/admin/users/{telegram_user_id}/audit",
    handlers.admin_list_user_audit,
    methods=["GET"],
    response_model=AuditPageOut,
)
router.add_api_route(
    "/api/admin/users/{telegram_user_id}/audit/{job_id}/message",
    handlers.admin_get_user_audit_message,
    methods=["GET"],
    response_model=AuditMessageOut,
)
router.add_api_route(
    "/api/admin/users",
    handlers.admin_list_users,
    methods=["GET"],
    response_model=AdminUserPageOut,
)
router.add_api_route(
    "/api/admin/users/{telegram_user_id}",
    handlers.admin_update_user,
    methods=["PATCH"],
    response_model=AdminUserOut,
)
router.add_api_route(
    "/api/admin/stats",
    handlers.admin_stats,
    methods=["GET"],
    response_model=AdminStatsOut,
)
