from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request

from autopost_manager.alerts import send_alert
from autopost_manager.config import get_settings
from autopost_manager.security import verify_webapp_init_data


def request_user_id(request: Request) -> int | None:
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        return None
    try:
        return verify_webapp_init_data(
            init_data,
            get_settings().bot_token,
            max_age_seconds=get_settings().telegram_init_data_max_age_seconds,
        )
    except ValueError:
        return None


async def alert_unhandled_errors(request: Request, call_next: Any) -> Any:
    try:
        return await call_next(request)
    except Exception as exc:
        await send_alert(
            title="Unhandled API exception",
            status="500",
            fields={
                "action": "api_request",
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "telegram_user_id": request_user_id(request),
                "error_type": type(exc).__name__,
                "error": exc,
            },
        )
        raise


async def security_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self' https://telegram.org https://*.telegram.org; "
        "script-src 'self' 'unsafe-inline' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://*.telegram.org https://api.telegram.org; "
        "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org;",
    )
    return response


def validate_runtime_settings() -> None:
    settings = get_settings()
    if settings.app_env != "local" and settings.allow_local_auth_bypass:
        raise RuntimeError("ALLOW_LOCAL_AUTH_BYPASS must be disabled outside local")
    if settings.app_env != "local" and not settings.app_encryption_key:
        raise RuntimeError("APP_ENCRYPTION_KEY is required outside local")
    if settings.allow_local_auth_bypass and not settings.local_dev_user_id:
        raise RuntimeError("LOCAL_DEV_USER_ID is required when local auth bypass is enabled")


def startup() -> None:
    validate_runtime_settings()
    get_settings().telegram_sessions_dir.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
    startup()
    yield
