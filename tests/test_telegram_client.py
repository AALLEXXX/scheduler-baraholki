from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from telethon.errors import FloodWaitError, SessionPasswordNeededError

from autopost_manager import telegram_client
from autopost_manager.models import SessionStatus

from conftest import make_session


class FakeMessage:
    id = 999


class AuthorizedClient:
    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False
        self.sent: list[tuple[int, str, str | None]] = []

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def is_user_authorized(self) -> bool:
        return True

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None):
        self.sent.append((chat_id, text, parse_mode))
        return FakeMessage()


class UnauthorizedClient(AuthorizedClient):
    async def is_user_authorized(self) -> bool:
        return False


class LoginClient(AuthorizedClient):
    def __init__(self, *, password_needed: bool = False) -> None:
        super().__init__()
        self.password_needed = password_needed
        self.sign_ins: list[dict[str, object]] = []

    async def send_code_request(self, phone: str):
        self.phone = phone
        return SimpleNamespace(phone_code_hash="sent-code-hash")

    async def sign_in(self, **kwargs):
        self.sign_ins.append(kwargs)
        if self.password_needed:
            raise SessionPasswordNeededError(request=None)

    async def get_me(self):
        return SimpleNamespace(id=777, username="telegramuser")


def test_build_client_uses_session_specific_api_credentials(monkeypatch, db_session) -> None:
    calls: dict[str, object] = {}

    class FakeTelegramClient:
        def __init__(self, session_path, api_id, api_hash) -> None:
            calls["session_path"] = session_path
            calls["api_id"] = api_id
            calls["api_hash"] = api_hash

    monkeypatch.setattr(telegram_client, "TelegramClient", FakeTelegramClient)
    session = make_session(db_session)
    session.api_id = 999999
    session.api_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    client = telegram_client.build_client(session)

    assert isinstance(client, FakeTelegramClient)
    assert calls == {
        "session_path": session.session_path,
        "api_id": 999999,
        "api_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }


def test_send_message_rate_limits_sends_and_updates_session(monkeypatch, db_session) -> None:
    session = make_session(
        db_session,
        owner_id=111,
        last_send_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    session.min_send_interval_seconds = 30
    db_session.commit()
    fake_client = AuthorizedClient()
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(telegram_client, "build_client", lambda _session: fake_client)
    monkeypatch.setattr(telegram_client.asyncio, "sleep", fake_sleep)

    message_id = asyncio.run(
        telegram_client.send_message_from_session(
            db=db_session,
            session=session,
            chat_id=-1001,
            text="hello",
            parse_mode="html",
        )
    )

    assert message_id == 999
    assert fake_client.connected is True
    assert fake_client.disconnected is True
    assert fake_client.sent == [(-1001, "hello", "html")]
    assert sleeps and 19 <= sleeps[0] <= 21
    assert session.status == SessionStatus.active
    assert session.last_send_at is not None


def test_send_message_marks_session_as_needing_login_when_unauthorized(
    monkeypatch,
    db_session,
) -> None:
    session = make_session(db_session, owner_id=111)
    db_session.commit()
    fake_client = UnauthorizedClient()

    monkeypatch.setattr(telegram_client, "build_client", lambda _session: fake_client)

    with pytest.raises(RuntimeError, match="needs login"):
        asyncio.run(
            telegram_client.send_message_from_session(
                db=db_session,
                session=session,
                chat_id=-1001,
                text="hello",
                parse_mode=None,
            )
        )

    assert fake_client.disconnected is True
    assert session.status == SessionStatus.needs_login


def test_classify_send_error_marks_flood_wait_session_limited(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    error = FloodWaitError(request=None, capture=42)

    message = telegram_client.classify_send_error(error, session)

    assert message == "FloodWait: wait 42 seconds"
    assert session.status == SessionStatus.limited


def test_classify_send_error_formats_generic_exception() -> None:
    assert telegram_client.classify_send_error(RuntimeError("boom")) == "RuntimeError: boom"


def test_list_dialogs_filters_groups_and_channels(monkeypatch, db_session) -> None:
    session = make_session(db_session)

    class DialogClient(AuthorizedClient):
        async def iter_dialogs(self, limit: int):
            assert limit == 300
            dialogs = [
                SimpleNamespace(
                    id=-1001,
                    name="Group",
                    is_group=True,
                    is_channel=False,
                    entity=SimpleNamespace(username="group"),
                ),
                SimpleNamespace(
                    id=-1002,
                    name="Channel",
                    is_group=False,
                    is_channel=True,
                    entity=SimpleNamespace(username=None),
                ),
                SimpleNamespace(
                    id=123,
                    name="Private",
                    is_group=False,
                    is_channel=False,
                    entity=SimpleNamespace(username="private"),
                ),
            ]
            for dialog in dialogs:
                yield dialog

    fake_client = DialogClient()
    monkeypatch.setattr(telegram_client, "build_client", lambda _session: fake_client)

    rows = asyncio.run(telegram_client.list_dialogs_from_session(session))

    assert rows == [
        {
            "telegram_chat_id": -1001,
            "title": "Group",
            "username": "group",
            "is_group": True,
            "is_channel": False,
        },
        {
            "telegram_chat_id": -1002,
            "title": "Channel",
            "username": None,
            "is_group": False,
            "is_channel": True,
        },
    ]
    assert fake_client.disconnected is True


def test_list_dialogs_raises_when_session_is_not_authorized(monkeypatch, db_session) -> None:
    session = make_session(db_session)
    fake_client = UnauthorizedClient()
    monkeypatch.setattr(telegram_client, "build_client", lambda _session: fake_client)

    with pytest.raises(RuntimeError, match="needs login"):
        asyncio.run(telegram_client.list_dialogs_from_session(session))

    assert fake_client.disconnected is True


def test_request_login_code_uses_client_and_disconnects(monkeypatch, db_session) -> None:
    session = make_session(db_session, phone="+123")
    fake_client = LoginClient()
    monkeypatch.setattr(telegram_client, "build_client", lambda _session: fake_client)

    code_hash = asyncio.run(telegram_client.request_login_code(session))

    assert code_hash == "sent-code-hash"
    assert fake_client.phone == "+123"
    assert fake_client.disconnected is True


def test_confirm_login_code_handles_success_and_password_needed(monkeypatch, db_session) -> None:
    session = make_session(db_session, phone="+123")
    session.phone_code_hash = "phone-hash"
    success_client = LoginClient()
    monkeypatch.setattr(telegram_client, "build_client", lambda _session: success_client)

    completed, me = asyncio.run(telegram_client.confirm_login_code(session, "11111"))

    assert completed is True
    assert me.id == 777
    assert success_client.sign_ins == [
        {"phone": "+123", "code": "11111", "phone_code_hash": "phone-hash"}
    ]
    assert success_client.disconnected is True

    password_client = LoginClient(password_needed=True)
    monkeypatch.setattr(telegram_client, "build_client", lambda _session: password_client)

    completed, me = asyncio.run(telegram_client.confirm_login_code(session, "22222"))

    assert completed is False
    assert me is None
    assert password_client.disconnected is True


def test_confirm_login_password_returns_user_and_disconnects(monkeypatch, db_session) -> None:
    session = make_session(db_session)
    fake_client = LoginClient()
    monkeypatch.setattr(telegram_client, "build_client", lambda _session: fake_client)

    me = asyncio.run(telegram_client.confirm_login_password(session, "secret"))

    assert me.id == 777
    assert fake_client.sign_ins == [{"password": "secret"}]
    assert fake_client.disconnected is True
