from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException, status

from autopost_manager.config import get_settings


def verify_webapp_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> int:
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing Telegram init data hash")

    auth_date = int(parsed.get("auth_date", "0"))
    if time.time() - auth_date > max_age_seconds:
        raise ValueError("Telegram init data is expired")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram init data hash")

    user = json.loads(parsed.get("user", "{}"))
    user_id = user.get("id")
    if not isinstance(user_id, int):
        raise ValueError("Missing Telegram user id")
    return user_id


def require_user(x_telegram_init_data: str | None = Header(default=None)) -> int:
    settings = get_settings()
    if settings.app_env == "local" and settings.allow_local_auth_bypass and not x_telegram_init_data:
        return settings.local_dev_user_id
    if not x_telegram_init_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing init data")
    try:
        telegram_id = verify_webapp_init_data(
            x_telegram_init_data,
            settings.bot_token,
            max_age_seconds=settings.telegram_init_data_max_age_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return telegram_id
