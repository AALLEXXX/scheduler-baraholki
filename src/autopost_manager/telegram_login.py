from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telethon.errors import SessionPasswordNeededError

from autopost_manager.models import TelegramSession
from autopost_manager.telegram_runtime import (
    disconnect_client,
    remember_client_session,
    session_lock,
    telegram_timeout,
)

BuildClient = Callable[[TelegramSession], Any]


@dataclass(frozen=True)
class LoginCodeRequest:
    phone_code_hash: str
    delivery_type: str
    next_delivery_type: str | None = None
    timeout: int | None = None


async def request_login_code(
    session: TelegramSession,
    *,
    force_sms: bool = False,
    build_client_func: BuildClient,
) -> LoginCodeRequest:
    async with session_lock(session.session_path):
        client = build_client_func(session)
        await telegram_timeout(client.connect(), 20)
        try:
            sent_code = await telegram_timeout(
                client.send_code_request(session.phone, force_sms=force_sms),
                30,
            )
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)
        next_type = getattr(sent_code, "next_type", None)
        return LoginCodeRequest(
            phone_code_hash=sent_code.phone_code_hash,
            delivery_type=type(sent_code.type).__name__,
            next_delivery_type=type(next_type).__name__ if next_type else None,
            timeout=getattr(sent_code, "timeout", None),
        )


async def confirm_login_code(
    session: TelegramSession,
    code: str,
    *,
    build_client_func: BuildClient,
) -> tuple[bool, object | None]:
    async with session_lock(session.session_path):
        client = build_client_func(session)
        await telegram_timeout(client.connect(), 20)
        try:
            try:
                await telegram_timeout(
                    client.sign_in(
                        phone=session.phone,
                        code=code,
                        phone_code_hash=session.phone_code_hash,
                    ),
                    30,
                )
            except SessionPasswordNeededError:
                return False, None
            me = await telegram_timeout(client.get_me(), 20)
            return True, me
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)


async def confirm_login_password(
    session: TelegramSession,
    password: str,
    *,
    build_client_func: BuildClient,
) -> object:
    async with session_lock(session.session_path):
        client = build_client_func(session)
        await telegram_timeout(client.connect(), 20)
        try:
            await telegram_timeout(client.sign_in(password=password), 30)
            return await telegram_timeout(client.get_me(), 20)
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)


async def logout_session_from_telegram(
    session: TelegramSession,
    *,
    build_client_func: BuildClient,
) -> None:
    async with session_lock(session.session_path):
        client = build_client_func(session)
        await telegram_timeout(client.connect(), 20)
        try:
            if await telegram_timeout(client.is_user_authorized(), 20):
                await telegram_timeout(client.log_out(), 30)
        finally:
            await disconnect_client(client)
