from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from autopost_manager.config import get_settings


def admin_only(message: Message) -> bool:
    return bool(message.from_user)


async def start(message: Message) -> None:
    settings = get_settings()
    if not admin_only(message):
        await message.answer("Access denied.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Open control panel",
                    web_app=WebAppInfo(url=settings.mini_app_url),
                )
            ]
        ]
    )
    await message.answer("Барахолки готовы. Открой панель и подключи Telegram-аккаунт.", reply_markup=keyboard)


async def status(message: Message) -> None:
    if not admin_only(message):
        await message.answer("Access denied.")
        return
    await message.answer("Сервис работает. Посты отправляются через подключенные аккаунты пользователей.")


async def run_bot() -> None:
    settings = get_settings()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.message.register(start, Command("start"))
    dp.message.register(status, Command("status"))
    dp.message.register(start, F.text == "panel")
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
