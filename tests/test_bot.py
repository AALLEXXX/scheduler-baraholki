from __future__ import annotations

import asyncio
from types import SimpleNamespace

from autopost_manager import bot as bot_module


class FakeMessage:
    def __init__(self, from_user=object()) -> None:
        self.from_user = from_user
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


def test_admin_only_requires_telegram_user() -> None:
    assert bot_module.admin_only(FakeMessage(from_user=object())) is True
    assert bot_module.admin_only(FakeMessage(from_user=None)) is False


def test_start_sends_mini_app_button(monkeypatch) -> None:
    monkeypatch.setattr(
        bot_module,
        "get_settings",
        lambda: SimpleNamespace(mini_app_url="https://example.com/scheduler/"),
    )
    message = FakeMessage()

    asyncio.run(bot_module.start(message))

    assert len(message.answers) == 1
    text, markup = message.answers[0]
    assert "Барахолки готовы" in text
    button = markup.inline_keyboard[0][0]
    assert button.text == "Open control panel"
    assert button.web_app.url == "https://example.com/scheduler/"


def test_start_rejects_message_without_user() -> None:
    message = FakeMessage(from_user=None)

    asyncio.run(bot_module.start(message))

    assert message.answers == [("Access denied.", None)]


def test_status_replies_with_service_state() -> None:
    message = FakeMessage()

    asyncio.run(bot_module.status(message))

    assert message.answers == [
        ("Сервис работает. Посты отправляются через подключенные аккаунты пользователей.", None)
    ]
