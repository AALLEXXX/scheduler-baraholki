from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from telethon import functions, types, utils

from autopost_manager.config import get_settings
from autopost_manager.models import TelegramSession
from autopost_manager.telegram_runtime import (
    disconnect_client,
    remember_client_session,
    session_lock,
    telegram_timeout,
)

BuildClient = Callable[[TelegramSession], Any]


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


async def list_dialog_folders_from_session(
    session: TelegramSession,
    *,
    build_client_func: BuildClient,
) -> list[dict[str, object]]:
    async with session_lock(session.session_path):
        client = build_client_func(session)
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


async def list_dialogs_from_session(
    session: TelegramSession,
    *,
    build_client_func: BuildClient,
) -> list[dict[str, object]]:
    async with session_lock(session.session_path):
        client = build_client_func(session)
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
