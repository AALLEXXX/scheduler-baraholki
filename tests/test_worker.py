from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from autopost_manager import worker
from autopost_manager.db import SessionLocal
from autopost_manager.models import JobStatus, PublishJob, SessionStatus

from conftest import make_chat, make_job, make_post, make_session


def test_choose_session_prefers_explicit_active_job_session(db_session) -> None:
    explicit = make_session(db_session, owner_id=111, phone="+111")
    fallback = make_session(db_session, owner_id=111, phone="+222")
    chat = make_chat(db_session, explicit)
    post = make_post(db_session, owner_id=111, session=fallback, chats=[chat])
    job = make_job(db_session, post, chat, session=explicit)
    db_session.commit()

    selected = worker.choose_session(db_session, job)

    assert selected.id == explicit.id


def test_choose_session_falls_back_to_owner_active_session(db_session) -> None:
    recent = make_session(
        db_session,
        owner_id=111,
        phone="+111",
        last_send_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    old = make_session(
        db_session,
        owner_id=111,
        phone="+222",
        last_send_at=datetime.now(UTC) - timedelta(hours=1),
    )
    inactive = make_session(db_session, owner_id=111, phone="+333", status=SessionStatus.paused)
    chat = make_chat(db_session, old)
    post = make_post(db_session, owner_id=111, session=None, chats=[chat])
    job = make_job(db_session, post, chat, session=None)
    db_session.commit()

    selected = worker.choose_session(db_session, job)

    assert selected.id == old.id
    assert selected.id not in {recent.id, inactive.id}


def test_process_one_job_success_marks_done(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session, telegram_chat_id=-1001)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat], body="hello")
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    async def fake_send_message_from_session(db, session, chat_id, text, parse_mode):
        assert chat_id == -1001
        assert text == "hello"
        assert parse_mode == "html"
        return 555

    monkeypatch.setattr(worker, "send_message_from_session", fake_send_message_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.done
        assert refreshed.attempts == 1
        assert refreshed.telegram_message_id == 555
        assert refreshed.last_error is None


def test_process_one_job_without_active_session_fails_job(db_session) -> None:
    session = make_session(db_session, owner_id=111, status=SessionStatus.paused)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.failed
        assert refreshed.attempts == 1
        assert refreshed.last_error == "No active session selected for job"


def test_process_one_job_records_send_error(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    async def failing_send_message_from_session(*_args, **_kwargs):
        raise RuntimeError("telegram exploded")

    monkeypatch.setattr(worker, "send_message_from_session", failing_send_message_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.failed
        assert refreshed.attempts == 1
        assert refreshed.last_error == "RuntimeError: telegram exploded"


def test_process_one_job_returns_false_when_queue_is_empty() -> None:
    assert asyncio.run(worker.process_one_job()) is False
