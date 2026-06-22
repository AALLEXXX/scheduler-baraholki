from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import aiohttp
from sqlalchemy.orm import Session
from telethon import TelegramClient, functions, types, utils
from telethon.errors import FloodWaitError, SessionPasswordNeededError

from autopost_manager.config import get_settings
from autopost_manager.models import Post, PostMedia, SessionStatus, TelegramSession

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


async def send_post_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    post: Post,
) -> int:
    media_items = sorted(post.media_items, key=lambda item: item.order_index)
    if not media_items:
        return await send_message_from_session(
            db=db,
            session=session,
            chat_id=chat_id,
            text=post.body,
            parse_mode=post.parse_mode,
        )

    return await send_media_from_session(
        db=db,
        session=session,
        chat_id=chat_id,
        media_items=media_items,
        text=post.body,
        parse_mode=post.parse_mode,
    )


async def send_media_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    media_items: list[PostMedia],
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
        temp_files: list[str] = []
        try:
            if not await client.is_user_authorized():
                session.status = SessionStatus.needs_login
                db.commit()
                raise RuntimeError("Telegram session needs login")

            files = [media.file_id for media in media_items]
            try:
                sent = await send_files_with_optional_text(
                    client=client,
                    chat_id=chat_id,
                    files=files,
                    text=text,
                    parse_mode=parse_mode,
                )
            except Exception:
                temp_files = [
                    await download_bot_file(media.file_id, media.media_type)
                    for media in media_items
                ]
                sent = await send_files_with_optional_text(
                    client=client,
                    chat_id=chat_id,
                    files=temp_files,
                    text=text,
                    parse_mode=parse_mode,
                )
        finally:
            for temp_file in temp_files:
                Path(temp_file).unlink(missing_ok=True)
            await client.disconnect()

        session.last_send_at = datetime.now(UTC)
        session.status = SessionStatus.active
        db.commit()
        return extract_sent_message_id(sent)


async def send_files_with_optional_text(
    *,
    client: TelegramClient,
    chat_id: int,
    files: list[str],
    text: str,
    parse_mode: str | None,
):
    caption = text if text and len(text) <= 1024 else None
    sent = await client.send_file(
        chat_id,
        files[0] if len(files) == 1 else files,
        caption=caption,
        parse_mode=parse_mode,
    )
    if text and not caption:
        text_message = await client.send_message(chat_id, text, parse_mode=parse_mode)
        return text_message
    return sent


def extract_sent_message_id(sent) -> int:
    if isinstance(sent, list):
        return int(sent[-1].id)
    return int(sent.id)


async def download_bot_file(file_id: str, media_type: str) -> str:
    settings = get_settings()
    suffix_by_type = {
        "photo": ".jpg",
        "video": ".mp4",
        "animation": ".mp4",
        "document": "",
    }
    async with aiohttp.ClientSession() as http:
        async with http.get(
            f"https://api.telegram.org/bot{settings.bot_token}/getFile",
            params={"file_id": file_id},
        ) as response:
            payload = await response.json()
            if not payload.get("ok"):
                raise RuntimeError(f"Could not resolve Telegram file: {payload}")
            file_path = payload["result"]["file_path"]

        suffix = Path(file_path).suffix or suffix_by_type.get(media_type, "")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = temp.name

        async with http.get(
            f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"
        ) as response:
            if response.status >= 400:
                raise RuntimeError(f"Could not download Telegram file: HTTP {response.status}")
            Path(temp_path).write_bytes(await response.read())

    return temp_path


async def delete_messages_from_session(
    session: TelegramSession,
    peer: str,
    message_ids: list[int],
) -> int:
    if not message_ids:
        return 0

    lock = _lock_for(session.session_path)
    async with lock:
        client = build_client(session)
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise RuntimeError("Telegram session needs login")
            entity = await client.get_entity(peer)
            await client.delete_messages(entity, message_ids, revoke=True)
        finally:
            await client.disconnect()
    return len(message_ids)


def text_from_telegram_title(value) -> str:
    if isinstance(value, str):
        return value
    text = getattr(value, "text", None)
    if text:
        return str(text)
    return str(value)


def peer_ids(values) -> set[int]:
    ids: set[int] = set()
    for value in values or []:
        try:
            ids.add(int(utils.get_peer_id(value)))
        except (TypeError, ValueError):
            continue
    return ids


def folder_chat_ids(folder, dialogs: list[dict[str, object]]) -> list[int]:
    include_ids = peer_ids(getattr(folder, "include_peers", [])) | peer_ids(
        getattr(folder, "pinned_peers", [])
    )
    exclude_ids = peer_ids(getattr(folder, "exclude_peers", []))
    dialog_ids = {int(dialog["telegram_chat_id"]) for dialog in dialogs}

    if include_ids:
        return sorted((include_ids & dialog_ids) - exclude_ids)

    selected: set[int] = set()
    include_groups = bool(getattr(folder, "groups", False))
    include_broadcasts = bool(getattr(folder, "broadcasts", False))
    for dialog in dialogs:
        chat_id = int(dialog["telegram_chat_id"])
        if include_groups and bool(dialog["is_group"]):
            selected.add(chat_id)
        if include_broadcasts and bool(dialog["is_channel"]) and not bool(dialog["is_group"]):
            selected.add(chat_id)
    return sorted(selected - exclude_ids)


async def list_dialog_folders_from_session(session: TelegramSession) -> list[dict[str, object]]:
    client = build_client(session)
    dialogs: list[dict[str, object]] = []
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram session needs login")

        async for dialog in client.iter_dialogs(limit=300):
            if not (dialog.is_group or dialog.is_channel):
                continue
            dialogs.append(
                {
                    "telegram_chat_id": int(dialog.id),
                    "is_group": bool(dialog.is_group),
                    "is_channel": bool(dialog.is_channel),
                }
            )

        folders = await client(functions.messages.GetDialogFiltersRequest())
        rows: list[dict[str, object]] = []
        for folder in folders:
            if not isinstance(folder, types.DialogFilter):
                continue
            chat_ids = folder_chat_ids(folder, dialogs)
            if not chat_ids:
                continue
            rows.append(
                {
                    "id": int(folder.id),
                    "title": text_from_telegram_title(folder.title),
                    "telegram_chat_ids": chat_ids,
                }
            )
        return rows
    finally:
        await client.disconnect()


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
