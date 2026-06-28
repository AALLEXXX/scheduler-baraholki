from __future__ import annotations

import asyncio
from uuid import UUID

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.messages import POST_SAVED_ACK_TEXT
from autopost_manager.models import Post
from autopost_manager.services.draft_parser import draft_input_from_message
from autopost_manager.services.draft_parser import extract_media
from autopost_manager.services.drafts import DraftLimitError, DraftService


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


def save_message_as_draft(message: Message) -> tuple[Post, bool]:
    settings = get_settings()
    draft_input = draft_input_from_message(message, settings)
    with SessionLocal() as db:
        return DraftService(db=db, settings=settings).create_or_update_draft(draft_input)


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
