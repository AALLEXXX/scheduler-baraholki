from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from autopost_manager.crypto import encrypt_session_string
from autopost_manager.models import Post, PostMedia, SessionStatus, TelegramSession
from autopost_manager.send_errors import classify_send_error_info
from autopost_manager.telegram_media import download_bot_file
from autopost_manager.telegram_runtime import build_client
from autopost_manager.telegram_send import TelegramSendResult
from autopost_manager.telegram_send import send_media_from_session as send_media_via_telegram
from autopost_manager.telegram_send import send_message_from_session as send_message_via_telegram
from autopost_manager.telegram_send import send_post_from_session as send_post_via_telegram

BuildClient = Callable[[TelegramSession], Any]
DownloadBotFile = Callable[[str, str], Awaitable[str]]
Sleep = Callable[[float], Awaitable[None]]


def apply_send_result(session: TelegramSession, result: TelegramSendResult) -> None:
    if result.session_string:
        session.session_string = encrypt_session_string(result.session_string)
    session.last_send_at = result.sent_at
    session.status = SessionStatus.active


def apply_send_error(session: TelegramSession, exc: Exception) -> None:
    send_error = classify_send_error_info(exc)
    if send_error.needs_login:
        session.status = SessionStatus.needs_login
    elif send_error.limited:
        session.status = SessionStatus.limited


async def send_message_from_session(
    session: TelegramSession,
    chat_id: int,
    text: str,
    parse_mode: str | None,
    *,
    build_client_func: BuildClient = build_client,
    sleep: Sleep = asyncio.sleep,
) -> int:
    try:
        result = await send_message_via_telegram(
            session=session,
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            build_client_func=build_client_func,
            sleep=sleep,
        )
    except Exception as exc:
        apply_send_error(session, exc)
        raise
    apply_send_result(session, result)
    return result.message_id


async def send_post_from_session(
    session: TelegramSession,
    chat_id: int,
    post: Post,
    *,
    build_client_func: BuildClient = build_client,
    download_bot_file_func: DownloadBotFile = download_bot_file,
    sleep: Sleep = asyncio.sleep,
) -> int:
    try:
        result = await send_post_via_telegram(
            session=session,
            chat_id=chat_id,
            post=post,
            build_client_func=build_client_func,
            download_bot_file_func=download_bot_file_func,
            sleep=sleep,
        )
    except Exception as exc:
        apply_send_error(session, exc)
        raise
    apply_send_result(session, result)
    return result.message_id


async def send_media_from_session(
    session: TelegramSession,
    chat_id: int,
    media_items: list[PostMedia],
    text: str,
    parse_mode: str | None,
    source_created_at: datetime | None = None,
    *,
    build_client_func: BuildClient = build_client,
    download_bot_file_func: DownloadBotFile = download_bot_file,
    sleep: Sleep = asyncio.sleep,
) -> int:
    try:
        result = await send_media_via_telegram(
            session=session,
            chat_id=chat_id,
            media_items=media_items,
            text=text,
            parse_mode=parse_mode,
            source_created_at=source_created_at,
            build_client_func=build_client_func,
            download_bot_file_func=download_bot_file_func,
            sleep=sleep,
        )
    except Exception as exc:
        apply_send_error(session, exc)
        raise
    apply_send_result(session, result)
    return result.message_id
