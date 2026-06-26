from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api_routes.helpers import add_dual_route
from autopost_manager.schemas import AdminStatsOut, AdminUserOut, AdminUserPageOut, AuditMessageOut, AuditPageOut

router = APIRouter()

add_dual_route(
    router,
    "/api/admin/users/{telegram_user_id}/audit",
    "/rest/autopost/admin/users/{telegram_user_id}/audit",
    handlers.admin_list_user_audit,
    methods=["GET"],
    response_model=AuditPageOut,
)
add_dual_route(
    router,
    "/api/admin/users/{telegram_user_id}/audit/{job_id}/message",
    "/rest/autopost/admin/users/{telegram_user_id}/audit/{job_id}/message",
    handlers.admin_get_user_audit_message,
    methods=["GET"],
    response_model=AuditMessageOut,
)
add_dual_route(
    router,
    "/api/admin/users",
    "/rest/autopost/admin/users",
    handlers.admin_list_users,
    methods=["GET"],
    response_model=AdminUserPageOut,
)
add_dual_route(
    router,
    "/api/admin/users/{telegram_user_id}",
    "/rest/autopost/admin/users/{telegram_user_id}",
    handlers.admin_update_user,
    methods=["PATCH"],
    response_model=AdminUserOut,
)
add_dual_route(
    router,
    "/api/admin/stats",
    "/rest/autopost/admin/stats",
    handlers.admin_stats,
    methods=["GET"],
    response_model=AdminStatsOut,
)
