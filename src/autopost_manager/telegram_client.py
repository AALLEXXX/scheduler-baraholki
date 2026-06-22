from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from autopost_manager.config import get_settings
from autopost_manager.models import SessionStatus, TelegramSession

_locks: dict[str, asyncio.Lock] = {}


def _lock_for(session_path: str) -> asyncio.Lock:
    if session_path not in _locks:
        _locks[session_path] = asyncio.Lock()
    return _locks[session_path]


async def send_message_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    text: str,
    parse_mode: str | None,
) -> int:
    settings = get_settings()
    lock = _lock_for(session.session_path)

    async with lock:
        now = datetime.now(UTC)
        if session.last_send_at:
            elapsed = (now - session.last_send_at).total_seconds()
            wait_seconds = max(0, session.min_send_interval_seconds - elapsed)
            if wait_seconds:
                await asyncio.sleep(wait_seconds)

        client = TelegramClient(
            session.session_path,
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
        async with client:
            if not await client.is_user_authorized():
                session.status = SessionStatus.needs_login
                db.commit()
                raise RuntimeError("Telegram session needs login")
            message = await client.send_message(chat_id, text, parse_mode=parse_mode)

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
