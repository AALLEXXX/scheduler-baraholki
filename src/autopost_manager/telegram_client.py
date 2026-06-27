from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy.orm import Session
from telethon import TelegramClient

from autopost_manager.models import Post, PostMedia, TelegramSession
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
from autopost_manager.services.telegram_delivery import send_media_from_session as service_send_media_from_session
from autopost_manager.services.telegram_delivery import send_message_from_session as service_send_message_from_session
from autopost_manager.services.telegram_delivery import send_post_from_session as service_send_post_from_session
from autopost_manager.telegram_runtime import build_client as runtime_build_client
from autopost_manager.telegram_runtime import legacy_session_string as runtime_legacy_session_string
from autopost_manager.telegram_send import find_forwardable_source_message_ids as telegram_find_forwardable_source_message_ids
from autopost_manager.telegram_send import is_outgoing_message as telegram_is_outgoing_message
from autopost_manager.telegram_send import message_distance as telegram_message_distance


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
    return await service_send_message_from_session(
        db=db,
        session=session,
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        build_client_func=build_client,
        sleep=asyncio.sleep,
    )


async def send_post_from_session(
    db: Session,
    session: TelegramSession,
    chat_id: int,
    post: Post,
) -> int:
    return await service_send_post_from_session(
        db=db,
        session=session,
        chat_id=chat_id,
        post=post,
        build_client_func=build_client,
        download_bot_file_func=download_bot_file,
        sleep=asyncio.sleep,
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
    return await service_send_media_from_session(
        db=db,
        session=session,
        chat_id=chat_id,
        media_items=media_items,
        text=text,
        parse_mode=parse_mode,
        source_created_at=source_created_at,
        build_client_func=build_client,
        download_bot_file_func=download_bot_file,
        sleep=asyncio.sleep,
    )


async def find_forwardable_source_message_ids(
    *,
    client,
    text: str,
    media_count: int,
    created_at: datetime | None,
) -> list[int]:
    return await telegram_find_forwardable_source_message_ids(
        client=client,
        text=text,
        media_count=media_count,
        created_at=created_at,
    )


def is_outgoing_message(message) -> bool:
    return telegram_is_outgoing_message(message)


def message_distance(message, reference: datetime | None) -> float:
    return telegram_message_distance(message, reference)


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
