from __future__ import annotations

from fastapi import APIRouter

from autopost_manager import api as handlers
from autopost_manager.api.routes import add_dual_route
from autopost_manager.schemas import AccountLoginOut, AccountPauseOut, AccountRevokeOut

router = APIRouter()

add_dual_route(
    router,
    "/api/account/start-login",
    ("/rpc/autopost/start-telegram-login", "/rpc/autopost/account/start-login"),
    handlers.start_account_login,
    methods=["POST"],
    response_model=AccountLoginOut,
)
add_dual_route(
    router,
    "/api/account/confirm-code",
    ("/rpc/autopost/confirm-telegram-code", "/rpc/autopost/account/confirm-code"),
    handlers.confirm_account_code,
    methods=["POST"],
    response_model=AccountLoginOut,
)
add_dual_route(
    router,
    "/api/account/confirm-password",
    ("/rpc/autopost/confirm-telegram-password", "/rpc/autopost/account/confirm-password"),
    handlers.confirm_account_password,
    methods=["POST"],
    response_model=AccountLoginOut,
)
add_dual_route(
    router,
    "/api/account/pause",
    ("/rpc/autopost/pause-autoposting", "/rpc/autopost/account/pause"),
    handlers.pause_account,
    methods=["POST"],
    response_model=AccountPauseOut,
)
add_dual_route(
    router,
    "/api/account/logout",
    ("/rpc/autopost/logout-account", "/rpc/autopost/account/logout"),
    handlers.logout_account,
    methods=["POST"],
    response_model=AccountPauseOut,
)
add_dual_route(
    router,
    "/api/account/resume",
    ("/rpc/autopost/resume-autoposting", "/rpc/autopost/account/resume"),
    handlers.resume_account,
    methods=["POST"],
    response_model=AccountPauseOut,
)
add_dual_route(
    router,
    "/api/account/revoke-session",
    ("/rpc/autopost/revoke-telegram-session", "/rpc/autopost/account/revoke-session"),
    handlers.revoke_account_session,
    methods=["POST"],
    response_model=AccountRevokeOut,
)
