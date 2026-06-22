from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session
from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError

from autopost_manager.config import get_settings
from autopost_manager.models import SessionStatus, TelegramSession

_locks: dict[str, asyncio.Lock] = {}


def _lock_for(session_path: str) -> asyncio.Lock:
    if session_path not in _locks:
        _locks[session_path] = asyncio.Lock()
    return _locks[session_path]


def build_client(session: TelegramSession) -> TelegramClient:
    settings = get_settings()
    api_id = session.api_id or settings.telegram_api_id
    api_hash = session.api_hash or settings.telegram_api_hash
    return TelegramClient(session.session_path, api_id, api_hash)


async def send_message_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    text: str,
    parse_mode: str | None,
) -> int:
    lock = _lock_for(session.session_path)

    async with lock:
        now = datetime.now(UTC)
        if session.last_send_at:
            elapsed = (now - session.last_send_at).total_seconds()
            wait_seconds = max(0, session.min_send_interval_seconds - elapsed)
            if wait_seconds:
                await asyncio.sleep(wait_seconds)

        client = build_client(session)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                session.status = SessionStatus.needs_login
                db.commit()
                raise RuntimeError("Telegram session needs login")
            message = await client.send_message(chat_id, text, parse_mode=parse_mode)
        finally:
            await client.disconnect()

        session.last_send_at = datetime.now(UTC)
        session.status = SessionStatus.active
        db.commit()
        return int(message.id)


def classify_send_error(exc: Exception, session: TelegramSession | None = None) -> str:
    if isinstance(exc, FloodWaitError):
        if session:
            session.status = SessionStatus.limited
        return f"FloodWait: wait {exc.seconds} seconds"
    return f"{exc.__class__.__name__}: {exc}"


async def list_dialogs_from_session(session: TelegramSession) -> list[dict[str, object]]:
    client = build_client(session)
    rows: list[dict[str, object]] = []
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram session needs login")

        async for dialog in client.iter_dialogs(limit=300):
            if not (dialog.is_group or dialog.is_channel):
                continue
            entity = dialog.entity
            rows.append(
                {
                    "telegram_chat_id": int(dialog.id),
                    "title": dialog.name,
                    "username": getattr(entity, "username", None),
                    "is_group": bool(dialog.is_group),
                    "is_channel": bool(dialog.is_channel),
                }
            )
    finally:
        await client.disconnect()
    return rows


async def request_login_code(session: TelegramSession) -> str:
    client = build_client(session)
    await client.connect()
    try:
        sent_code = await client.send_code_request(session.phone)
    finally:
        await client.disconnect()
    return sent_code.phone_code_hash


async def confirm_login_code(session: TelegramSession, code: str) -> tuple[bool, object | None]:
    client = build_client(session)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=session.phone,
                code=code,
                phone_code_hash=session.phone_code_hash,
            )
        except SessionPasswordNeededError:
            return False, None
        me = await client.get_me()
        return True, me
    finally:
        await client.disconnect()


async def confirm_login_password(session: TelegramSession, password: str) -> object:
    client = build_client(session)
    await client.connect()
    try:
        await client.sign_in(password=password)
        return await client.get_me()
    finally:
        await client.disconnect()
