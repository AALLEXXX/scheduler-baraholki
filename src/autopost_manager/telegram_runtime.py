from __future__ import annotations

import asyncio
from contextlib import suppress
import fcntl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession

from autopost_manager.config import get_settings
from autopost_manager.crypto import decrypt_session_string, encrypt_session_string
from autopost_manager.models import TelegramSession

_locks: dict[str, asyncio.Lock] = {}


def _lock_for(session_path: str) -> asyncio.Lock:
    if session_path not in _locks:
        _locks[session_path] = asyncio.Lock()
    return _locks[session_path]


@asynccontextmanager
async def session_lock(session_path: str) -> AsyncIterator[None]:
    lock = _lock_for(session_path)
    async with lock:
        lock_path = Path(f"{session_path}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = lock_path.open("a")
        try:
            await asyncio.to_thread(fcntl.flock, lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


def build_client(session: TelegramSession, client_class=TelegramClient) -> TelegramClient:
    settings = get_settings()
    api_id = session.api_id or settings.telegram_api_id
    api_hash = session.api_hash or settings.telegram_api_hash
    session_string = decrypt_session_string(session.session_string)
    legacy_string = legacy_session_string(session.session_path) if not session_string else ""
    if legacy_string:
        session_string = legacy_string
    return client_class(StringSession(session_string or ""), api_id, api_hash)


def legacy_session_string(session_path: str | None) -> str:
    if not session_path or not Path(f"{session_path}.session").exists():
        return ""
    try:
        legacy_session = SQLiteSession(session_path)
        try:
            return StringSession.save(legacy_session)
        finally:
            legacy_session.close()
    except Exception:
        return ""


def client_session_string(client) -> str | None:
    client_session = getattr(client, "session", None)
    if not client_session:
        return None
    session_string = StringSession.save(client_session)
    if session_string:
        return session_string
    return None


def remember_client_session(session: TelegramSession, client) -> None:
    session_string = client_session_string(client)
    if session_string:
        session.session_string = encrypt_session_string(session_string)


async def telegram_timeout(awaitable, timeout_seconds: int | None = None):
    timeout = timeout_seconds or get_settings().telegram_operation_timeout_seconds
    return await asyncio.wait_for(awaitable, timeout=timeout)


async def disconnect_client(client) -> None:
    with suppress(Exception):
        await asyncio.wait_for(client.disconnect(), timeout=10)
