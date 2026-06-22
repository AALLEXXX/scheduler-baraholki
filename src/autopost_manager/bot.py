from __future__ import annotations

import asyncio
import re
from html import unescape

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import func, select

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal, create_schema
from autopost_manager.models import Post, PostMedia, PostStatus, ScheduleKind


def admin_only(message: Message) -> bool:
    return bool(message.from_user)


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
    if not admin_only(message):
        await message.answer("Access denied.")
        return

    await message.answer(
        "Барахолки готовы. Пришлите сюда готовый пост или откройте панель.",
        reply_markup=panel_keyboard(),
    )


async def status(message: Message) -> None:
    if not admin_only(message):
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


def find_album_post(db, owner_id: int, media_group_id: str) -> Post | None:
    return db.scalars(
        select(Post)
        .join(PostMedia)
        .where(Post.created_by_telegram_id == owner_id)
        .where(Post.status == PostStatus.draft)
        .where(PostMedia.media_group_id == media_group_id)
        .order_by(Post.created_at.desc())
    ).first()


def save_message_as_draft(message: Message) -> tuple[Post, bool]:
    if not message.from_user:
        raise ValueError("Message has no user")

    owner_id = message.from_user.id
    html_body = html_body_from_message(message)
    media = extract_media(message)
    media_type = media[0] if media else None
    media_group_id = message.media_group_id

    with SessionLocal() as db:
        post = find_album_post(db, owner_id, media_group_id) if media_group_id else None
        created = post is None

        if not post:
            post = Post(
                title=title_from_message(message, html_body, media_type),
                body=html_body,
                parse_mode="html",
                status=PostStatus.draft,
                schedule_kind=ScheduleKind.once,
                timezone="Asia/Tbilisi",
                session_strategy="fixed",
                created_by_telegram_id=owner_id,
                source_bot_chat_id=message.chat.id,
                source_bot_message_id=message.message_id,
                source_media_group_id=media_group_id,
            )
            db.add(post)
            db.flush()
        elif html_body and not post.body:
            post.body = html_body
            post.title = title_from_message(message, html_body, media_type)

        if media:
            existing_media = db.scalars(
                select(PostMedia)
                .where(PostMedia.post_id == post.id)
                .where(PostMedia.source_bot_chat_id == message.chat.id)
                .where(PostMedia.source_bot_message_id == message.message_id)
            ).first()
            if not existing_media:
                order_index = db.scalar(
                    select(func.count(PostMedia.id)).where(PostMedia.post_id == post.id)
                )
                db.add(
                    PostMedia(
                        post_id=post.id,
                        source_bot_chat_id=message.chat.id,
                        source_bot_message_id=message.message_id,
                        media_group_id=media_group_id,
                        media_type=media[0],
                        file_id=media[1],
                        file_unique_id=media[2],
                        order_index=int(order_index or 0),
                    )
                )

        db.commit()
        db.refresh(post)
        return post, created


def save_ack_message(post_id, ack_message: Message) -> None:
    with SessionLocal() as db:
        post = db.get(Post, post_id)
        if not post:
            return
        post.ack_bot_chat_id = ack_message.chat.id
        post.ack_bot_message_id = ack_message.message_id
        db.commit()


async def save_draft(message: Message) -> None:
    if not message.from_user:
        return
    if message.text and message.text.startswith("/"):
        return
    if not (message.text or message.caption or extract_media(message)):
        return

    post, created = save_message_as_draft(message)
    if created:
        ack_message = await message.answer(
            "Пост сохранён как черновик. Откройте панель, чтобы выбрать группы и расписание.",
            reply_markup=panel_keyboard(),
        )
        save_ack_message(post.id, ack_message)


async def run_bot() -> None:
    create_schema()
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
