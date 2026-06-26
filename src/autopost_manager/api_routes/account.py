from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.schemas import AccountLoginOut, AccountPauseOut, AccountRevokeOut

router = APIRouter()

router.add_api_route(
    "/api/account/start-login",
    handlers.start_account_login,
    methods=["POST"],
    response_model=AccountLoginOut,
)
router.add_api_route(
    "/api/account/confirm-code",
    handlers.confirm_account_code,
    methods=["POST"],
    response_model=AccountLoginOut,
)
router.add_api_route(
    "/api/account/confirm-password",
    handlers.confirm_account_password,
    methods=["POST"],
    response_model=AccountLoginOut,
)
router.add_api_route(
    "/api/account/pause",
    handlers.pause_account,
    methods=["POST"],
    response_model=AccountPauseOut,
)
router.add_api_route(
    "/api/account/logout",
    handlers.logout_account,
    methods=["POST"],
    response_model=AccountPauseOut,
)
router.add_api_route(
    "/api/account/resume",
    handlers.resume_account,
    methods=["POST"],
    response_model=AccountPauseOut,
)
router.add_api_route(
    "/api/account/revoke-session",
    handlers.revoke_account_session,
    methods=["POST"],
    response_model=AccountRevokeOut,
)
