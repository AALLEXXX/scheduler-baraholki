from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from autopost_manager.config import get_settings
from autopost_manager.models import Post, PostMedia, SessionStatus, TelegramSession
from autopost_manager.telegram_cleanup_client import near_datetime, normalize_plain_text
from autopost_manager.telegram_media import extract_sent_message_id
from autopost_manager.telegram_media import send_files_with_optional_text
from autopost_manager.telegram_runtime import (
    disconnect_client,
    remember_client_session,
    session_lock,
    telegram_timeout,
)

BuildClient = Callable[[TelegramSession], Any]
DownloadBotFile = Callable[[str, str], Awaitable[str]]
Sleep = Callable[[float], Awaitable[None]]


async def send_message_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    text: str,
    parse_mode: str | None,
    *,
    build_client_func: BuildClient,
    sleep: Sleep = asyncio.sleep,
) -> int:
    async with session_lock(session.session_path):
        now = datetime.now(UTC)
        if session.last_send_at:
            elapsed = (now - session.last_send_at).total_seconds()
            wait_seconds = max(0, session.min_send_interval_seconds - elapsed)
            if wait_seconds:
                await sleep(wait_seconds)

        client = build_client_func(session)
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
    *,
    build_client_func: BuildClient,
    download_bot_file_func: DownloadBotFile,
    sleep: Sleep = asyncio.sleep,
) -> int:
    media_items = sorted(post.media_items, key=lambda item: item.order_index)
    if not media_items:
        return await send_message_from_session(
            db=db,
            session=session,
            chat_id=chat_id,
            text=post.body,
            parse_mode=post.parse_mode,
            build_client_func=build_client_func,
            sleep=sleep,
        )

    return await send_media_from_session(
        db=db,
        session=session,
        chat_id=chat_id,
        media_items=media_items,
        text=post.body,
        parse_mode=post.parse_mode,
        source_created_at=post.created_at,
        build_client_func=build_client_func,
        download_bot_file_func=download_bot_file_func,
        sleep=sleep,
    )


async def send_media_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    media_items: list[PostMedia],
    text: str,
    parse_mode: str | None,
    source_created_at: datetime | None = None,
    *,
    build_client_func: BuildClient,
    download_bot_file_func: DownloadBotFile,
    sleep: Sleep = asyncio.sleep,
) -> int:
    async with session_lock(session.session_path):
        now = datetime.now(UTC)
        if session.last_send_at:
            elapsed = (now - session.last_send_at).total_seconds()
            wait_seconds = max(0, session.min_send_interval_seconds - elapsed)
            if wait_seconds:
                await sleep(wait_seconds)

        client = build_client_func(session)
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
                        await download_bot_file_func(media.file_id, media.media_type)
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
    client: Any,
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
    grouped: dict[int, list[Any]] = {}

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


def is_outgoing_message(message: Any) -> bool:
    return bool(getattr(message, "out", False) or getattr(message, "outgoing", False))


def message_distance(message: Any, reference: datetime | None) -> float:
    message_date = getattr(message, "date", None)
    if not message_date or not reference:
        return 0.0
    if message_date.tzinfo is None:
        message_date = message_date.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return abs((message_date - reference).total_seconds())
