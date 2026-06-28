from __future__ import annotations

import re
from html import unescape

from aiogram.types import Message

from autopost_manager.config import Settings
from autopost_manager.services.drafts import DraftInput, DraftLimitError, DraftMediaInput


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value)).strip()


def title_from_message(message: Message, html_body: str, media_type: str | None) -> str:
    raw = message.text or message.caption or strip_html(html_body)
    raw = " ".join(raw.split())
    if raw:
        return raw[:120]
    if media_type:
        return {
            "photo": "Фото из Telegram",
            "video": "Видео из Telegram",
            "animation": "Анимация из Telegram",
            "document": "Файл из Telegram",
        }.get(media_type, "Медиа из Telegram")
    return "Пост из Telegram"


def html_body_from_message(message: Message) -> str:
    if message.text:
        return getattr(message, "html_text", None) or message.text
    if message.caption:
        return (
            getattr(message, "html_text", None)
            or getattr(message, "html_caption", None)
            or message.caption
        )
    return ""


def extract_media(message: Message) -> tuple[str, str, str | None] | None:
    if getattr(message, "photo", None):
        photo = message.photo[-1]
        return "photo", photo.file_id, photo.file_unique_id
    if getattr(message, "video", None):
        return "video", message.video.file_id, message.video.file_unique_id
    if getattr(message, "animation", None):
        return "animation", message.animation.file_id, message.animation.file_unique_id
    if getattr(message, "document", None):
        return "document", message.document.file_id, message.document.file_unique_id
    return None


def media_file_size(message: Message) -> int | None:
    media = (
        getattr(message, "video", None)
        or getattr(message, "animation", None)
        or getattr(message, "document", None)
    )
    return getattr(media, "file_size", None)


def validate_message_limits(message: Message, html_body: str, settings: Settings) -> None:
    if len(html_body) > 4096:
        raise DraftLimitError("Пост слишком длинный. Максимум — 4096 символов.")
    file_size = media_file_size(message)
    if file_size is not None and file_size > settings.max_bot_file_bytes:
        raise DraftLimitError("Файл слишком большой. Загрузите медиа меньшего размера.")


def draft_input_from_message(message: Message, settings: Settings) -> DraftInput:
    if not message.from_user:
        raise ValueError("Message has no user")

    owner_id = message.from_user.id
    html_body = html_body_from_message(message)
    validate_message_limits(message, html_body, settings)
    media = extract_media(message)
    media_type = media[0] if media else None
    return DraftInput(
        owner_telegram_id=owner_id,
        title=title_from_message(message, html_body, media_type),
        html_body=html_body,
        source_bot_chat_id=message.chat.id,
        source_bot_message_id=message.message_id,
        source_media_group_id=message.media_group_id,
        media=DraftMediaInput(media_type=media[0], file_id=media[1], file_unique_id=media[2])
        if media
        else None,
    )
