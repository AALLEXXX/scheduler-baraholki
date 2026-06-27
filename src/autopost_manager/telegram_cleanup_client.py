from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from typing import Any

from autopost_manager.config import get_settings
from autopost_manager.models import TelegramSession
from autopost_manager.telegram_runtime import (
    disconnect_client,
    remember_client_session,
    session_lock,
    telegram_timeout,
)

BuildClient = Callable[[TelegramSession], Any]


@dataclass(frozen=True)
class TelegramMessageSnapshot:
    text: str
    has_media: bool
    date: datetime | None = None


async def delete_messages_from_session(
    session: TelegramSession,
    peer: str,
    message_ids: list[int],
    *,
    build_client_func: BuildClient,
    match_texts: set[str] | None = None,
    ack_text: str | None = None,
    created_at: datetime | None = None,
    media_count: int = 0,
) -> int:
    if not message_ids and not match_texts and not ack_text and not media_count:
        return 0

    async with session_lock(session.session_path):
        client = build_client_func(session)
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


async def fetch_message_snapshot_from_session(
    session: TelegramSession,
    peer: int,
    message_id: int,
    *,
    build_client_func: BuildClient,
) -> TelegramMessageSnapshot | None:
    async with session_lock(session.session_path):
        client = build_client_func(session)
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


get_message_from_session = fetch_message_snapshot_from_session


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
    client: Any,
    entity: Any,
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
