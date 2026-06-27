from __future__ import annotations

import asyncio
from collections.abc import Sequence

from telethon import TelegramClient
from telethon.sessions import StringSession

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.models import SessionStatus, TelegramSession


async def login_session(
    owner_telegram_id: int,
    name: str,
    phone: str,
    *,
    telegram_client_class=TelegramClient,
) -> None:
    settings = get_settings()
    settings.telegram_sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(settings.telegram_sessions_dir / name.replace(" ", "_").lower())
    string_session = StringSession()

    async with telegram_client_class(
        string_session,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    ) as client:
        await client.start(phone=phone)
        me = await client.get_me()
        session_string = StringSession.save(client.session)

    with SessionLocal() as db:
        existing = (
            db.query(TelegramSession)
            .filter(
                TelegramSession.owner_telegram_id == owner_telegram_id,
                TelegramSession.name == name,
            )
            .one_or_none()
        )
        if existing:
            existing.owner_telegram_id = owner_telegram_id
            existing.phone = phone
            existing.telegram_user_id = me.id
            existing.username = me.username
            existing.status = SessionStatus.active
            existing.session_path = session_path
            existing.session_string = session_string
        else:
            db.add(
                TelegramSession(
                    owner_telegram_id=owner_telegram_id,
                    name=name,
                    phone=phone,
                    telegram_user_id=me.id,
                    username=me.username,
                    status=SessionStatus.active,
                    session_path=session_path,
                    session_string=session_string,
                    min_send_interval_seconds=settings.default_min_send_interval_seconds,
                )
            )
        db.commit()

    print(f"Authorized session '{name}' as {me.id} @{me.username or ''}".strip())


def main(argv: Sequence[str] | None = None) -> None:
    import sys

    args = list(argv or sys.argv[1:])
    if len(args) != 3:
        raise SystemExit("Usage: autopost-login-session <owner-telegram-id> <session-name> <phone>")
    asyncio.run(login_session(int(args[0]), args[1], args[2]))
