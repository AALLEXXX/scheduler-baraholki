from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError
from telethon.sessions import StringSession

from autopost_manager import session_login
from autopost_manager.db import SessionLocal
from autopost_manager.models import SessionStatus, TelegramSession


class FakeTelegramClient:
    starts: list[str] = []

    def __init__(self, session_path, api_id, api_hash) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = StringSession()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def start(self, phone: str) -> None:
        self.starts.append(phone)

    async def get_me(self):
        return type("Me", (), {"id": 999, "username": "loginuser"})()


def test_login_session_creates_authorized_session(monkeypatch) -> None:
    monkeypatch.setattr(session_login, "TelegramClient", FakeTelegramClient)

    asyncio.run(session_login.login_session(111, "Main Account", "+10000000000"))

    with SessionLocal() as db:
        session = db.query(TelegramSession).one()
        assert session.owner_telegram_id == 111
        assert session.name == "Main Account"
        assert session.phone == "+10000000000"
        assert session.telegram_user_id == 999
        assert session.username == "loginuser"
        assert session.status == SessionStatus.active
        assert session.session_path.endswith("main_account")


def test_login_session_updates_existing_session(monkeypatch) -> None:
    monkeypatch.setattr(session_login, "TelegramClient", FakeTelegramClient)
    with SessionLocal() as db:
        db.add(
            TelegramSession(
                owner_telegram_id=111,
                name="Main Account",
                phone="+old",
                telegram_user_id=1,
                username="old",
                status=SessionStatus.paused,
                session_path="/tmp/old",
                min_send_interval_seconds=30,
            )
        )
        db.commit()

    asyncio.run(session_login.login_session(111, "Main Account", "+20000000000"))

    with SessionLocal() as db:
        sessions = db.query(TelegramSession).all()
        assert len(sessions) == 1
        assert sessions[0].owner_telegram_id == 111
        assert sessions[0].phone == "+20000000000"
        assert sessions[0].telegram_user_id == 999
        assert sessions[0].status == SessionStatus.active


def test_login_session_scopes_session_name_to_owner(monkeypatch) -> None:
    monkeypatch.setattr(session_login, "TelegramClient", FakeTelegramClient)
    with SessionLocal() as db:
        db.add(
            TelegramSession(
                owner_telegram_id=222,
                name="Main Account",
                phone="+old",
                telegram_user_id=2,
                username="other",
                status=SessionStatus.active,
                session_path="/tmp/other",
                min_send_interval_seconds=30,
            )
        )
        db.commit()

    asyncio.run(session_login.login_session(111, "Main Account", "+10000000000"))

    with SessionLocal() as db:
        sessions = db.query(TelegramSession).order_by(TelegramSession.owner_telegram_id).all()
        assert [session.owner_telegram_id for session in sessions] == [111, 222]
        assert [session.name for session in sessions] == ["Main Account", "Main Account"]


def test_session_name_is_unique_per_owner(db_session) -> None:
    db_session.add_all(
        [
            TelegramSession(
                owner_telegram_id=111,
                name="Main Account",
                phone="+111",
                telegram_user_id=111,
                username="first",
                status=SessionStatus.active,
                session_path="/tmp/first",
                min_send_interval_seconds=30,
            ),
            TelegramSession(
                owner_telegram_id=111,
                name="Main Account",
                phone="+222",
                telegram_user_id=222,
                username="second",
                status=SessionStatus.active,
                session_path="/tmp/second",
                min_send_interval_seconds=30,
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
