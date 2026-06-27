from __future__ import annotations

import asyncio
import re
from html import unescape
from uuid import UUID

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.messages import POST_SAVED_ACK_TEXT
from autopost_manager.models import Post
from autopost_manager.services.drafts import DraftInput, DraftLimitError, DraftMediaInput, DraftService


def has_telegram_sender(message: Message) -> bool:
    return message.from_user is not None


def panel_keyboard() -> InlineKeyboardMarkup:
    settings = get_settings()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Open control panel",
                    web_app=WebAppInfo(url=settings.mini_app_url),
                )
            ]
        ]
    )


async def start(message: Message) -> None:
    if not has_telegram_sender(message):
        await message.answer("Access denied.")
        return

    await message.answer(
        "Барахолки готовы. Пришлите сюда готовый пост или откройте панель.",
        reply_markup=panel_keyboard(),
    )


async def status(message: Message) -> None:
    if not has_telegram_sender(message):
        await message.answer("Access denied.")
        return
    await message.answer("Сервис работает. Посты отправляются через подключенные аккаунты пользователей.")


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


def validate_message_limits(message: Message, html_body: str) -> None:
    settings = get_settings()
    if len(html_body) > 4096:
        raise DraftLimitError("Пост слишком длинный. Максимум — 4096 символов.")
    file_size = media_file_size(message)
    if file_size is not None and file_size > settings.max_bot_file_bytes:
        raise DraftLimitError("Файл слишком большой. Загрузите медиа меньшего размера.")


def draft_input_from_message(message: Message) -> DraftInput:
    if not message.from_user:
        raise ValueError("Message has no user")

    owner_id = message.from_user.id
    html_body = html_body_from_message(message)
    validate_message_limits(message, html_body)
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


def save_message_as_draft(message: Message) -> tuple[Post, bool]:
    draft_input = draft_input_from_message(message)
    with SessionLocal() as db:
        return DraftService(db=db, settings=get_settings()).create_or_update_draft(draft_input)


def save_ack_message(post_id: UUID, ack_message: Message) -> None:
    with SessionLocal() as db:
        DraftService(db=db, settings=get_settings()).save_ack_message(
            post_id,
            ack_chat_id=ack_message.chat.id,
            ack_message_id=ack_message.message_id,
        )


async def save_draft(message: Message) -> None:
    if not message.from_user:
        return
    if message.text and message.text.startswith("/"):
        return
    if not (message.text or message.caption or extract_media(message)):
        return

    try:
        post, created = save_message_as_draft(message)
    except DraftLimitError as exc:
        await message.answer(str(exc))
        return
    if created:
        ack_message = await message.answer(
            POST_SAVED_ACK_TEXT,
            reply_markup=panel_keyboard(),
        )
        save_ack_message(post.id, ack_message)


async def run_bot() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.message.register(start, Command("start"))
    dp.message.register(status, Command("status"))
    dp.message.register(start, F.text == "panel")
    dp.message.register(save_draft)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
