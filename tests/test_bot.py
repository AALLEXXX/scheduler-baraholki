from __future__ import annotations

import asyncio
from types import SimpleNamespace

from autopost_manager import bot as bot_module
from autopost_manager.db import SessionLocal
from autopost_manager.models import Post, PostMedia, PostStatus


class FakeMessage:
    def __init__(
        self,
        *,
        from_user=object(),
        text: str | None = None,
        html_text: str | None = None,
        caption: str | None = None,
        photo=None,
        media_group_id: str | None = None,
        message_id: int = 1,
    ) -> None:
        self.from_user = from_user
        self.text = text
        self.html_text = html_text
        self.caption = caption
        self.photo = photo
        self.video = None
        self.animation = None
        self.document = None
        self.media_group_id = media_group_id
        self.message_id = message_id
        self.chat = SimpleNamespace(id=from_user.id if hasattr(from_user, "id") else 111)
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


def test_save_message_as_draft_persists_formatted_text() -> None:
    message = FakeMessage(
        from_user=SimpleNamespace(id=111),
        text="Bold text",
        html_text="<b>Bold text</b>",
        message_id=10,
    )

    post, created = bot_module.save_message_as_draft(message)

    assert created is True
    with SessionLocal() as db:
        saved = db.get(Post, post.id)
        assert saved.created_by_telegram_id == 111
        assert saved.status == PostStatus.draft
        assert saved.body == "<b>Bold text</b>"
        assert saved.media_items == []


def test_save_message_as_draft_persists_photo_media() -> None:
    message = FakeMessage(
        from_user=SimpleNamespace(id=111),
        caption="Caption",
        html_text="<i>Caption</i>",
        photo=[
            SimpleNamespace(file_id="small", file_unique_id="small-unique"),
            SimpleNamespace(file_id="large", file_unique_id="large-unique"),
        ],
        message_id=11,
    )

    post, created = bot_module.save_message_as_draft(message)

    assert created is True
    with SessionLocal() as db:
        saved = db.get(Post, post.id)
        assert saved.body == "<i>Caption</i>"
        [media] = saved.media_items
        assert media.media_type == "photo"
        assert media.file_id == "large"
        assert media.file_unique_id == "large-unique"


def test_save_message_as_draft_groups_album_messages_into_one_post() -> None:
    first = FakeMessage(
        from_user=SimpleNamespace(id=111),
        caption="Album caption",
        html_text="<b>Album caption</b>",
        photo=[SimpleNamespace(file_id="first", file_unique_id="first-unique")],
        media_group_id="album-1",
        message_id=20,
    )
    second = FakeMessage(
        from_user=SimpleNamespace(id=111),
        photo=[SimpleNamespace(file_id="second", file_unique_id="second-unique")],
        media_group_id="album-1",
        message_id=21,
    )

    first_post, first_created = bot_module.save_message_as_draft(first)
    second_post, second_created = bot_module.save_message_as_draft(second)

    assert first_created is True
    assert second_created is False
    assert second_post.id == first_post.id
    with SessionLocal() as db:
        posts = db.query(Post).all()
        media = db.query(PostMedia).order_by(PostMedia.order_index).all()
        assert len(posts) == 1
        assert posts[0].body == "<b>Album caption</b>"
        assert [item.file_id for item in media] == ["first", "second"]


def test_save_draft_ignores_commands() -> None:
    message = FakeMessage(from_user=SimpleNamespace(id=111), text="/start", message_id=30)

    asyncio.run(bot_module.save_draft(message))

    with SessionLocal() as db:
        assert db.query(Post).count() == 0
