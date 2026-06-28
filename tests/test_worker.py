from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from autopost_manager import worker
from autopost_manager.db import SessionLocal
from autopost_manager.models import JobStatus, PublishJob, SessionStatus, UserSettings

from conftest import make_chat, make_job, make_media, make_post, make_session


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

    async def fake_send_post_from_session(session, chat_id, post):
        assert chat_id == -1001
        assert post.body == "hello"
        assert post.parse_mode == "html"
        return 555

    monkeypatch.setattr(worker, "send_post_from_session", fake_send_post_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.done
        assert refreshed.attempts == 1
        assert refreshed.telegram_message_id == 555
        assert refreshed.last_error is None
        assert refreshed.locked_at is None
        assert refreshed.locked_until is None
        assert refreshed.worker_id is None
        assert refreshed.completed_at is not None


def test_process_one_job_skips_globally_paused_owner(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.add(UserSettings(telegram_user_id=111, autopost_paused=True))
    db_session.commit()

    processed = asyncio.run(worker.process_one_job())

    assert processed is False
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.pending
        assert refreshed.attempts == 0


def test_process_one_job_cancels_if_owner_is_paused_after_pick(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    def pause_owner_before_send(db, selected_job):
        db.add(UserSettings(telegram_user_id=111, autopost_paused=True))
        db.commit()
        db.refresh(selected_job)
        return selected_job.session

    async def fail_if_called(*args, **kwargs):
        raise AssertionError("send_post_from_session must not be called while autopost is paused")

    monkeypatch.setattr(worker, "choose_active_session_for_job", pause_owner_before_send)
    monkeypatch.setattr(worker, "send_post_from_session", fail_if_called)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.cancelled
        assert refreshed.attempts == 1
        assert refreshed.last_error == "Autoposting paused by user"


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

    async def failing_send_post_from_session(*_args, **_kwargs):
        raise RuntimeError("telegram exploded")

    monkeypatch.setattr(worker, "send_post_from_session", failing_send_post_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.pending
        assert refreshed.attempts == 1
        assert refreshed.last_error == "RuntimeError: telegram exploded"
        assert refreshed.next_attempt_at is not None


def test_recover_stale_processing_jobs_moves_job_back_to_pending(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    job.status = JobStatus.processing
    job.locked_at = datetime.now(UTC) - timedelta(minutes=2)
    job.locked_until = datetime.now(UTC) - timedelta(minutes=1)
    job.worker_id = "test-worker"
    db_session.commit()

    recovered = worker.recover_stale_processing_jobs(db_session, datetime.now(UTC))

    assert recovered == 1
    assert job.status == JobStatus.pending
    assert job.locked_at is None
    assert job.locked_until is None
    assert job.worker_id is None
    assert job.next_attempt_at is not None
    assert job.last_error == "Recovered stale processing job"


def test_process_one_job_does_not_retry_write_forbidden_errors(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    async def forbidden_send_post_from_session(*_args, **_kwargs):
        raise RuntimeError("Chat write forbidden: user is banned or not allowed to post")

    monkeypatch.setattr(worker, "send_post_from_session", forbidden_send_post_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.failed
        assert refreshed.attempts == 1
        assert refreshed.next_attempt_at is None
        assert "Chat write forbidden" in refreshed.last_error


def test_process_one_job_marks_session_needing_login_on_auth_error(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    async def unauthorized_send_post_from_session(*_args, **_kwargs):
        raise RuntimeError("Telegram session needs login")

    monkeypatch.setattr(worker, "send_post_from_session", unauthorized_send_post_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed_job = db.get(PublishJob, job.id)
        refreshed_session = db.get(type(session), session.id)
        assert refreshed_job.status == JobStatus.failed
        assert refreshed_session.status == SessionStatus.needs_login


def test_process_one_job_marks_session_limited_on_flood_wait(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    async def flood_wait_send_post_from_session(*_args, **_kwargs):
        from telethon.errors import FloodWaitError

        raise FloodWaitError(request=None, capture=42)

    monkeypatch.setattr(worker, "send_post_from_session", flood_wait_send_post_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed_job = db.get(PublishJob, job.id)
        refreshed_session = db.get(type(session), session.id)
        assert refreshed_job.status == JobStatus.pending
        assert refreshed_job.next_attempt_at is not None
        assert refreshed_session.status == SessionStatus.limited


def test_process_one_job_sends_alert_with_job_context(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111, username="alice")
    chat = make_chat(db_session, session, title="Target Chat", telegram_chat_id=-1001)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat], body="Alert post")
    make_job(db_session, post, chat, session=session)
    db_session.commit()
    alerts: list[dict] = []

    async def failing_send_post_from_session(*_args, **_kwargs):
        raise RuntimeError("telegram exploded")

    async def fake_send_alert(**kwargs):
        alerts.append(kwargs)

    monkeypatch.setattr(worker, "send_post_from_session", failing_send_post_from_session)
    monkeypatch.setattr(worker, "send_alert", fake_send_alert)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["title"] == "Publish job issue"
    assert alert["status"] == "pending"
    assert alert["fields"]["action"] == "send_post"
    assert alert["fields"]["owner_telegram_id"] == 111
    assert alert["fields"]["target_telegram_chat_id"] == -1001
    assert alert["fields"]["target_title"] == "Target Chat"
    assert alert["fields"]["post_title"] == "Alert post"
    assert alert["fields"]["error"] == "RuntimeError: telegram exploded"


def test_process_one_job_alert_uses_selected_fallback_session(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111, username="fallback")
    chat = make_chat(db_session, session, title="Target Chat", telegram_chat_id=-1001)
    post = make_post(db_session, owner_id=111, session=None, chats=[chat], body="Fallback alert post")
    make_job(db_session, post, chat, session=None)
    db_session.commit()
    alerts: list[dict] = []

    async def failing_send_post_from_session(*_args, **_kwargs):
        raise RuntimeError("telegram exploded")

    async def fake_send_alert(**kwargs):
        alerts.append(kwargs)

    monkeypatch.setattr(worker, "send_post_from_session", failing_send_post_from_session)
    monkeypatch.setattr(worker, "send_alert", fake_send_alert)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    assert len(alerts) == 1
    assert alerts[0]["fields"]["session_id"] == session.id
    assert alerts[0]["fields"]["session_status"] == SessionStatus.active.value


def test_process_one_job_returns_false_when_queue_is_empty() -> None:
    assert asyncio.run(worker.process_one_job()) is False


def test_process_one_job_passes_media_post_to_sender(monkeypatch, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session, telegram_chat_id=-1001)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat], body="caption")
    make_media(db_session, post, media_type="photo", file_id="photo-id")
    job = make_job(db_session, post, chat, session=session)
    db_session.commit()

    async def fake_send_post_from_session(session, chat_id, post):
        assert chat_id == -1001
        assert post.media_items[0].file_id == "photo-id"
        return 777

    monkeypatch.setattr(worker, "send_post_from_session", fake_send_post_from_session)

    processed = asyncio.run(worker.process_one_job())

    assert processed is True
    with SessionLocal() as db:
        refreshed = db.get(PublishJob, job.id)
        assert refreshed.status == JobStatus.done
        assert refreshed.telegram_message_id == 777
