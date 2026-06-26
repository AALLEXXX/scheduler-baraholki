from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session
from telethon import TelegramClient

from autopost_manager.config import get_settings
from autopost_manager.models import Post, PostMedia, SessionStatus, TelegramSession
from autopost_manager.send_errors import classify_send_error as format_send_error
from autopost_manager.telegram_cleanup_client import TelegramMessageSnapshot
from autopost_manager.telegram_cleanup_client import closest_ack_message_id as telegram_closest_ack_message_id
from autopost_manager.telegram_cleanup_client import delete_messages_from_session as telegram_delete_messages_from_session
from autopost_manager.telegram_cleanup_client import find_dialog_message_ids as telegram_find_dialog_message_ids
from autopost_manager.telegram_cleanup_client import get_message_from_session as telegram_get_message_from_session
from autopost_manager.telegram_cleanup_client import near_datetime as telegram_near_datetime
from autopost_manager.telegram_cleanup_client import normalize_plain_text as telegram_normalize_plain_text
from autopost_manager.telegram_dialogs import folder_chat_ids as telegram_folder_chat_ids
from autopost_manager.telegram_dialogs import list_dialog_folders_from_session as telegram_list_dialog_folders_from_session
from autopost_manager.telegram_dialogs import list_dialogs_from_session as telegram_list_dialogs_from_session
from autopost_manager.telegram_dialogs import peer_ids as telegram_peer_ids
from autopost_manager.telegram_dialogs import text_from_telegram_title as telegram_text_from_telegram_title
from autopost_manager.telegram_login import LoginCodeRequest
from autopost_manager.telegram_login import confirm_login_code as telegram_confirm_login_code
from autopost_manager.telegram_login import confirm_login_password as telegram_confirm_login_password
from autopost_manager.telegram_login import logout_session_from_telegram as telegram_logout_session_from_telegram
from autopost_manager.telegram_login import request_login_code as telegram_request_login_code
from autopost_manager.telegram_media import download_bot_file as telegram_download_bot_file
from autopost_manager.telegram_media import extract_sent_message_id as telegram_extract_sent_message_id
from autopost_manager.telegram_media import send_files_with_optional_text as telegram_send_files_with_optional_text
from autopost_manager.telegram_runtime import (
    disconnect_client,
    remember_client_session,
    session_lock,
    telegram_timeout,
)
from autopost_manager.telegram_runtime import build_client as runtime_build_client
from autopost_manager.telegram_runtime import legacy_session_string as runtime_legacy_session_string


def build_client(session: TelegramSession) -> TelegramClient:
    return runtime_build_client(session, client_class=TelegramClient)


def legacy_session_string(session_path: str | None) -> str:
    return runtime_legacy_session_string(session_path)


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
                raise RuntimeError("Telegram session needs login")
            message = await telegram_timeout(
                client.send_message(chat_id, text, parse_mode=parse_mode),
            )
        finally:
            remember_client_session(session, client)
            await disconnect_client(client)

        session.last_send_at = datetime.now(UTC)
        session.status = SessionStatus.active
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
    return await telegram_send_files_with_optional_text(
        client=client,
        chat_id=chat_id,
        files=files,
        text=text,
        parse_mode=parse_mode,
    )


def extract_sent_message_id(sent) -> int:
    return telegram_extract_sent_message_id(sent)


async def download_bot_file(file_id: str, media_type: str) -> str:
    return await telegram_download_bot_file(file_id, media_type)


async def delete_messages_from_session(
    session: TelegramSession,
    peer: str,
    message_ids: list[int],
    match_texts: set[str] | None = None,
    ack_text: str | None = None,
    created_at: datetime | None = None,
    media_count: int = 0,
) -> int:
    return await telegram_delete_messages_from_session(
        session=session,
        peer=peer,
        message_ids=message_ids,
        match_texts=match_texts,
        ack_text=ack_text,
        created_at=created_at,
        media_count=media_count,
        build_client_func=build_client,
    )


async def get_message_from_session(
    session: TelegramSession,
    peer: int,
    message_id: int,
) -> TelegramMessageSnapshot | None:
    return await telegram_get_message_from_session(
        session=session,
        peer=peer,
        message_id=message_id,
        build_client_func=build_client,
    )


def normalize_plain_text(value: str | None) -> str:
    return telegram_normalize_plain_text(value)


def near_datetime(value: datetime | None, reference: datetime | None, seconds: int = 1200) -> bool:
    return telegram_near_datetime(value, reference, seconds)


async def find_dialog_message_ids(
    *,
    client,
    entity,
    match_texts: set[str],
    ack_text: str | None = None,
    created_at: datetime | None,
    media_count: int,
) -> set[int]:
    return await telegram_find_dialog_message_ids(
        client=client,
        entity=entity,
        match_texts=match_texts,
        ack_text=ack_text,
        created_at=created_at,
        media_count=media_count,
    )


def closest_ack_message_id(
    *,
    ack_candidates: list[tuple[datetime | None, int]],
    source_candidates: list[tuple[datetime | None, int]],
    media_ids: set[int],
    created_at: datetime | None,
) -> int | None:
    return telegram_closest_ack_message_id(
        ack_candidates=ack_candidates,
        source_candidates=source_candidates,
        media_ids=media_ids,
        created_at=created_at,
    )


def text_from_telegram_title(value) -> str:
    return telegram_text_from_telegram_title(value)


def peer_ids(values) -> set[int]:
    return telegram_peer_ids(values)


def folder_chat_ids(folder, dialogs: list[dict[str, object]]) -> list[int]:
    return telegram_folder_chat_ids(folder, dialogs)


def classify_send_error(exc: Exception) -> str:
    return format_send_error(exc)


async def list_dialog_folders_from_session(session: TelegramSession) -> list[dict[str, object]]:
    return await telegram_list_dialog_folders_from_session(session, build_client_func=build_client)


async def list_dialogs_from_session(session: TelegramSession) -> list[dict[str, object]]:
    return await telegram_list_dialogs_from_session(session, build_client_func=build_client)


async def request_login_code(session: TelegramSession, *, force_sms: bool = False) -> LoginCodeRequest:
    return await telegram_request_login_code(session, force_sms=force_sms, build_client_func=build_client)


async def confirm_login_code(session: TelegramSession, code: str) -> tuple[bool, object | None]:
    return await telegram_confirm_login_code(session, code, build_client_func=build_client)


async def confirm_login_password(session: TelegramSession, password: str) -> object:
    return await telegram_confirm_login_password(session, password, build_client_func=build_client)


async def logout_session_from_telegram(session: TelegramSession) -> None:
    await telegram_logout_session_from_telegram(session, build_client_func=build_client)
