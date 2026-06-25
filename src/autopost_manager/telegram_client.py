from __future__ import annotations

import asyncio
import fcntl
import re
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from pathlib import Path

import aiohttp
from sqlalchemy.orm import Session
from telethon import TelegramClient, functions, types, utils
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.sessions import SQLiteSession, StringSession

from autopost_manager.config import get_settings
from autopost_manager.crypto import decrypt_session_string, encrypt_session_string
from autopost_manager.models import Post, PostMedia, SessionStatus, TelegramSession

_locks: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class LoginCodeRequest:
    phone_code_hash: str
    delivery_type: str
    next_delivery_type: str | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class TelegramMessageSnapshot:
    text: str
    has_media: bool
    date: datetime | None = None


def _lock_for(session_path: str) -> asyncio.Lock:
    if session_path not in _locks:
        _locks[session_path] = asyncio.Lock()
    return _locks[session_path]


@asynccontextmanager
async def session_lock(session_path: str):
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


def build_client(session: TelegramSession) -> TelegramClient:
    settings = get_settings()
    api_id = session.api_id or settings.telegram_api_id
    api_hash = session.api_hash or settings.telegram_api_hash
    session_string = decrypt_session_string(session.session_string)
    legacy_string = legacy_session_string(session.session_path) if not session_string else ""
    if legacy_string:
        session_string = legacy_string
        session.session_string = encrypt_session_string(legacy_string)
    return TelegramClient(StringSession(session_string or ""), api_id, api_hash)


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


def remember_client_session(session: TelegramSession, client) -> None:
    client_session = getattr(client, "session", None)
    if not client_session:
        return
    session_string = StringSession.save(client_session)
    if session_string:
        session.session_string = encrypt_session_string(session_string)


async def telegram_timeout(awaitable, timeout_seconds: int | None = None):
    timeout = timeout_seconds or get_settings().telegram_operation_timeout_seconds
    return await asyncio.wait_for(awaitable, timeout=timeout)


async def disconnect_client(client) -> None:
    try:
        await asyncio.wait_for(client.disconnect(), timeout=10)
    except Exception:
        pass


async def send_message_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    text: str,
    parse_mode: str | None,
) -> int:
    async with session_lock(session.session_path):
        now = datetime.now(UTC)
        if session.last_send_at:
            elapsed = (now - session.last_send_at).total_seconds()
            wait_seconds = max(0, session.min_send_interval_seconds - elapsed)
            if wait_seconds:
                await asyncio.sleep(wait_seconds)

        client = build_client(session)
        await telegram_timeout(client.connect(), 20)
        try:
            if not await telegram_timeout(client.is_user_authorized(), 20):
                session.status = SessionStatus.needs_login
                db.commit()
                raise RuntimeError("Telegram session needs login")
            message = await telegram_timeout(
                client.send_message(chat_id, text, parse_mode=parse_mode),
            )
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)

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
        source_created_at=post.created_at,
    )


async def send_media_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    media_items: list[PostMedia],
    text: str,
    parse_mode: str | None,
    source_created_at: datetime | None = None,
) -> int:
    async with session_lock(session.session_path):
        now = datetime.now(UTC)
        if session.last_send_at:
            elapsed = (now - session.last_send_at).total_seconds()
            wait_seconds = max(0, session.min_send_interval_seconds - elapsed)
            if wait_seconds:
                await asyncio.sleep(wait_seconds)

        client = build_client(session)
        await telegram_timeout(client.connect(), 20)
        temp_files: list[str] = []
        try:
            if not await telegram_timeout(client.is_user_authorized(), 20):
                session.status = SessionStatus.needs_login
                db.commit()
                raise RuntimeError("Telegram session needs login")

            source_message_ids = []
            if len(text) > 1024:
                source_message_ids = await find_forwardable_source_message_ids(
                    client=client,
                    text=text,
                    media_count=len(media_items),
                    created_at=source_created_at,
                )

            if source_message_ids:
                bot_peer = f"@{get_settings().bot_username.lstrip('@')}"
                entity = await telegram_timeout(client.get_entity(bot_peer), 20)
                sent = await telegram_timeout(
                    client.forward_messages(
                        chat_id,
                        messages=source_message_ids[0]
                        if len(source_message_ids) == 1
                        else source_message_ids,
                        from_peer=entity,
                        drop_author=True,
                    )
                )
            else:
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
            remember_client_session(session, client)
            await disconnect_client(client)

        session.last_send_at = datetime.now(UTC)
        session.status = SessionStatus.active
        db.commit()
        return extract_sent_message_id(sent)


async def find_forwardable_source_message_ids(
    *,
    client,
    text: str,
    media_count: int,
    created_at: datetime | None,
) -> list[int]:
    if not text or not media_count:
        return []

    bot_peer = f"@{get_settings().bot_username.lstrip('@')}"
    entity = await telegram_timeout(client.get_entity(bot_peer), 20)
    normalized_text = normalize_plain_text(text)
    if not normalized_text:
        return []

    single_candidates: list[tuple[float, list[int]]] = []
    grouped: dict[int, list] = {}

    async with asyncio.timeout(get_settings().telegram_operation_timeout_seconds):
        async for message in client.iter_messages(entity, limit=160):
            if not is_outgoing_message(message):
                continue
            if not near_datetime(getattr(message, "date", None), created_at):
                continue
            if not getattr(message, "media", None):
                continue

            grouped_id = getattr(message, "grouped_id", None)
            if grouped_id:
                grouped.setdefault(int(grouped_id), []).append(message)
                continue

            raw_text = normalize_plain_text(
                getattr(message, "raw_text", None) or getattr(message, "message", None)
            )
            if media_count == 1 and raw_text == normalized_text:
                single_candidates.append((message_distance(message, created_at), [int(message.id)]))

    for messages in grouped.values():
        if len(messages) != media_count:
            continue
        has_text = any(
            normalize_plain_text(getattr(message, "raw_text", None) or getattr(message, "message", None))
            == normalized_text
            for message in messages
        )
        if not has_text:
            continue
        ids = sorted(int(message.id) for message in messages)
        single_candidates.append((min(message_distance(message, created_at) for message in messages), ids))

    if not single_candidates:
        return []
    return min(single_candidates, key=lambda candidate: candidate[0])[1]


def is_outgoing_message(message) -> bool:
    return bool(getattr(message, "out", False) or getattr(message, "outgoing", False))


def message_distance(message, reference: datetime | None) -> float:
    message_date = getattr(message, "date", None)
    if not message_date or not reference:
        return 0.0
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return abs((message_date - reference).total_seconds())


async def send_files_with_optional_text(
    *,
    client: TelegramClient,
    chat_id: int,
    files: list[str],
    text: str,
    parse_mode: str | None,
):
    caption = text if text and len(text) <= 1024 else None
    sent = await telegram_timeout(
        client.send_file(
            chat_id,
            files[0] if len(files) == 1 else files,
            caption=caption,
            parse_mode=parse_mode,
        ),
        180,
    )
    if text and not caption:
        text_message = await telegram_timeout(client.send_message(chat_id, text, parse_mode=parse_mode))
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
    max_bytes = get_settings().max_bot_file_bytes
    timeout = aiohttp.ClientTimeout(total=120, sock_connect=20, sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout) as http:
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
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise RuntimeError("Telegram file is too large")
            downloaded = 0
            with Path(temp_path).open("wb") as output:
                async for chunk in response.content.iter_chunked(1024 * 256):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise RuntimeError("Telegram file is too large")
                    output.write(chunk)

    return temp_path


async def delete_messages_from_session(
    session: TelegramSession,
    peer: str,
    message_ids: list[int],
    match_texts: set[str] | None = None,
    ack_text: str | None = None,
    created_at: datetime | None = None,
    media_count: int = 0,
) -> int:
    if not message_ids and not match_texts and not ack_text and not media_count:
        return 0

    async with session_lock(session.session_path):
        client = build_client(session)
        await telegram_timeout(client.connect(), 20)
        try:
            if not await telegram_timeout(client.is_user_authorized(), 20):
                raise RuntimeError("Telegram session needs login")
            entity = await telegram_timeout(client.get_entity(peer), 20)
            matched_ids = await find_dialog_message_ids(
                client=client,
                entity=entity,
                match_texts=match_texts or set(),
                ack_text=ack_text,
                created_at=created_at,
                media_count=media_count,
            )
            ids_to_delete = matched_ids or set(message_ids)
            await telegram_timeout(client.delete_messages(entity, sorted(ids_to_delete), revoke=True))
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)
    return len(ids_to_delete)


async def get_message_from_session(
    session: TelegramSession,
    peer: int,
    message_id: int,
) -> TelegramMessageSnapshot | None:
    async with session_lock(session.session_path):
        client = build_client(session)
        await telegram_timeout(client.connect(), 20)
        try:
            if not await telegram_timeout(client.is_user_authorized(), 20):
                raise RuntimeError("Telegram session needs login")
            message = await telegram_timeout(client.get_messages(peer, ids=message_id), 30)
            if not message:
                return None
            return TelegramMessageSnapshot(
                text=normalize_plain_text(
                    getattr(message, "raw_text", None) or getattr(message, "message", None)
                ),
                has_media=bool(getattr(message, "media", None)),
                date=getattr(message, "date", None),
            )
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)


def normalize_plain_text(value: str | None) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", unescape(value or "")).split())


def near_datetime(value: datetime | None, reference: datetime | None, seconds: int = 1200) -> bool:
    if not value or not reference:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return abs((value - reference).total_seconds()) <= seconds


async def find_dialog_message_ids(
    *,
    client,
    entity,
    match_texts: set[str],
    ack_text: str | None = None,
    created_at: datetime | None,
    media_count: int,
) -> set[int]:
    normalized_texts = {normalize_plain_text(text) for text in match_texts if normalize_plain_text(text)}
    normalized_ack_text = normalize_plain_text(ack_text)
    matched_ids: set[int] = set()
    source_candidates: list[tuple[datetime | None, int]] = []
    ack_candidates: list[tuple[datetime | None, int]] = []
    media_candidates: list[tuple[float, int]] = []

    async with asyncio.timeout(get_settings().telegram_operation_timeout_seconds):
        async for message in client.iter_messages(entity, limit=120):
            if not near_datetime(getattr(message, "date", None), created_at):
                continue

            raw_text = normalize_plain_text(
                getattr(message, "raw_text", None) or getattr(message, "message", None)
            )
            if raw_text and raw_text in normalized_texts:
                message_id = int(message.id)
                matched_ids.add(message_id)
                source_candidates.append((getattr(message, "date", None), message_id))
            elif raw_text and normalized_ack_text and raw_text == normalized_ack_text:
                ack_candidates.append((getattr(message, "date", None), int(message.id)))

            if media_count and getattr(message, "media", None):
                distance = 0.0
                message_date = getattr(message, "date", None)
                if message_date and created_at:
                    if message_date.tzinfo is None:
                        message_date = message_date.replace(tzinfo=UTC)
                    reference = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
                    distance = abs((message_date - reference).total_seconds())
                media_candidates.append((distance, int(message.id)))

    for _distance, message_id in sorted(media_candidates)[:media_count]:
        matched_ids.add(message_id)

    ack_id = closest_ack_message_id(
        ack_candidates=ack_candidates,
        source_candidates=source_candidates,
        media_ids=matched_ids,
        created_at=created_at,
    )
    if ack_id:
        matched_ids.add(ack_id)
    return matched_ids


def closest_ack_message_id(
    *,
    ack_candidates: list[tuple[datetime | None, int]],
    source_candidates: list[tuple[datetime | None, int]],
    media_ids: set[int],
    created_at: datetime | None,
) -> int | None:
    if not ack_candidates:
        return None

    source_ids = [message_id for _date, message_id in source_candidates]
    if media_ids:
        source_ids.extend(media_ids)
    if source_ids:
        anchor_id = max(source_ids)
        later_acks = [candidate for candidate in ack_candidates if candidate[1] > anchor_id]
        if later_acks:
            return min(later_acks, key=lambda candidate: candidate[1] - anchor_id)[1]

    if created_at:
        reference = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)

        def distance(candidate: tuple[datetime | None, int]) -> float:
            date, _message_id = candidate
            if not date:
                return float("inf")
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            return abs((date - reference).total_seconds())

        return min(ack_candidates, key=distance)[1]

    return min(ack_candidates, key=lambda candidate: candidate[1])[1]


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
    async with session_lock(session.session_path):
        client = build_client(session)
        dialogs: list[dict[str, object]] = []
        await telegram_timeout(client.connect(), 20)
        try:
            if not await telegram_timeout(client.is_user_authorized(), 20):
                raise RuntimeError("Telegram session needs login")

            async with asyncio.timeout(get_settings().telegram_operation_timeout_seconds):
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

            folder_response = await telegram_timeout(client(functions.messages.GetDialogFiltersRequest()))
            folders = getattr(folder_response, "filters", folder_response)
            rows: list[dict[str, object]] = []
            for folder in folders:
                if not isinstance(folder, (types.DialogFilter, types.DialogFilterChatlist)):
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
            remember_client_session(session, client)
            await disconnect_client(client)


def classify_send_error(exc: Exception, session: TelegramSession | None = None) -> str:
    if isinstance(exc, FloodWaitError):
        if session:
            session.status = SessionStatus.limited
        return f"FloodWait: wait {exc.seconds} seconds"
    return f"{exc.__class__.__name__}: {exc}"


async def list_dialogs_from_session(session: TelegramSession) -> list[dict[str, object]]:
    async with session_lock(session.session_path):
        client = build_client(session)
        rows: list[dict[str, object]] = []
        await telegram_timeout(client.connect(), 20)
        try:
            if not await telegram_timeout(client.is_user_authorized(), 20):
                raise RuntimeError("Telegram session needs login")

            async with asyncio.timeout(get_settings().telegram_operation_timeout_seconds):
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
            remember_client_session(session, client)
            await disconnect_client(client)
        return rows


async def request_login_code(session: TelegramSession, *, force_sms: bool = False) -> LoginCodeRequest:
    async with session_lock(session.session_path):
        client = build_client(session)
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


async def confirm_login_code(session: TelegramSession, code: str) -> tuple[bool, object | None]:
    async with session_lock(session.session_path):
        client = build_client(session)
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


async def confirm_login_password(session: TelegramSession, password: str) -> object:
    async with session_lock(session.session_path):
        client = build_client(session)
        await telegram_timeout(client.connect(), 20)
        try:
            await telegram_timeout(client.sign_in(password=password), 30)
            return await telegram_timeout(client.get_me(), 20)
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)


async def logout_session_from_telegram(session: TelegramSession) -> None:
    async with session_lock(session.session_path):
        client = build_client(session)
        await telegram_timeout(client.connect(), 20)
        try:
            if await telegram_timeout(client.is_user_authorized(), 20):
                await telegram_timeout(client.log_out(), 30)
        finally:
            await disconnect_client(client)
