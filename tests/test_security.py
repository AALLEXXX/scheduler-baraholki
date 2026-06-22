from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from autopost_manager.security import verify_webapp_init_data


BOT_TOKEN = "1234567890:TEST_BOT_TOKEN_VALUE"


def make_init_data(
    *,
    user: dict[str, object] | None = None,
    auth_date: int | None = None,
    bot_token: str = BOT_TOKEN,
    tamper_hash: bool = False,
) -> str:
    payload = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAE-test-query",
        "user": json.dumps(user or {"id": 111, "first_name": "Alex"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    payload["hash"] = "0" * 64 if tamper_hash else calculated_hash
    return urlencode(payload)


def test_verify_webapp_init_data_accepts_valid_signed_payload() -> None:
    init_data = make_init_data(user={"id": 7569215208, "username": "owner"})

    assert verify_webapp_init_data(init_data, BOT_TOKEN) == 7569215208


def test_verify_webapp_init_data_rejects_invalid_hash() -> None:
    init_data = make_init_data(tamper_hash=True)

    with pytest.raises(ValueError, match="Invalid Telegram init data hash"):
        verify_webapp_init_data(init_data, BOT_TOKEN)


def test_verify_webapp_init_data_rejects_expired_payload() -> None:
    init_data = make_init_data(auth_date=1)

    with pytest.raises(ValueError, match="expired"):
        verify_webapp_init_data(init_data, BOT_TOKEN, max_age_seconds=60)


def test_verify_webapp_init_data_requires_integer_user_id() -> None:
    init_data = make_init_data(user={"username": "missing_id"})

    with pytest.raises(ValueError, match="Missing Telegram user id"):
        verify_webapp_init_data(init_data, BOT_TOKEN)


def test_verify_webapp_init_data_requires_hash() -> None:
    init_data = urlencode(
        {
            "auth_date": str(int(time.time())),
            "user": json.dumps({"id": 111}),
        }
    )

    with pytest.raises(ValueError, match="Missing Telegram init data hash"):
        verify_webapp_init_data(init_data, BOT_TOKEN)
