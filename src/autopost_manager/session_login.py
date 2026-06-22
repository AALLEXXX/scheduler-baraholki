from __future__ import annotations

import asyncio
import sys

from telethon import TelegramClient

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal, create_schema
from autopost_manager.models import SessionStatus, TelegramSession


async def login_session(name: str, phone: str) -> None:
    create_schema()
    settings = get_settings()
    settings.telegram_sessions_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(settings.telegram_sessions_dir / name.replace(" ", "_").lower())

    async with TelegramClient(
        session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    ) as client:
        await client.start(phone=phone)
        me = await client.get_me()

    with SessionLocal() as db:
        existing = db.query(TelegramSession).filter(TelegramSession.name == name).one_or_none()
        if existing:
            existing.phone = phone
            existing.telegram_user_id = me.id
            existing.username = me.username
            existing.status = SessionStatus.active
            existing.session_path = session_path
        else:
            db.add(
                TelegramSession(
                    name=name,
                    phone=phone,
                    telegram_user_id=me.id,
                    username=me.username,
                    status=SessionStatus.active,
                    session_path=session_path,
                    min_send_interval_seconds=settings.default_min_send_interval_seconds,
                )
            )
        db.commit()

    print(f"Authorized session '{name}' as {me.id} @{me.username or ''}".strip())


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: autopost-login-session <session-name> <phone>")
    asyncio.run(login_session(sys.argv[1], sys.argv[2]))


if __name__ == "__main__":
    main()
