from __future__ import annotations

from datetime import UTC, datetime, timedelta

from autopost_manager import scheduler
from autopost_manager.db import SessionLocal
from autopost_manager.models import JobStatus, Post, PostStatus, PublishJob, ScheduleKind

from conftest import make_chat, make_post, make_session


def as_aware(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def test_enqueue_due_once_post_creates_jobs_for_all_targets_and_archives(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    first_chat = make_chat(db_session, session, title="First")
    second_chat = make_chat(db_session, session, title="Second")
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[first_chat, second_chat],
        schedule_kind=ScheduleKind.once,
        next_run_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.commit()

    created = scheduler.enqueue_due_posts()

    assert created == 2
    with SessionLocal() as db:
        refreshed = db.get(Post, post.id)
        jobs = db.query(PublishJob).order_by(PublishJob.target_chat_id).all()
        assert refreshed.status == PostStatus.archived
        assert {job.target_chat_id for job in jobs} == {first_chat.id, second_chat.id}
        assert {job.status for job in jobs} == {JobStatus.pending}
        assert {job.session_id for job in jobs} == {session.id}


def test_enqueue_due_interval_post_creates_job_and_moves_next_run_forward(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    old_next_run = datetime.now(UTC) - timedelta(minutes=2)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        schedule_kind=ScheduleKind.interval,
        next_run_at=old_next_run,
        interval_minutes=45,
    )
    db_session.commit()

    created = scheduler.enqueue_due_posts()

    assert created == 1
    with SessionLocal() as db:
        refreshed = db.get(Post, post.id)
        assert refreshed.status == PostStatus.scheduled
        assert as_aware(refreshed.next_run_at) > datetime.now(UTC) + timedelta(minutes=40)
        assert db.query(PublishJob).count() == 1


def test_enqueue_due_daily_post_moves_to_next_day(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    old_next_run = datetime.now(UTC) - timedelta(seconds=1)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        schedule_kind=ScheduleKind.daily,
        next_run_at=old_next_run,
    )
    db_session.commit()

    created = scheduler.enqueue_due_posts()

    assert created == 1
    with SessionLocal() as db:
        refreshed = db.get(Post, post.id)
        assert refreshed.status == PostStatus.scheduled
        assert as_aware(refreshed.next_run_at) == old_next_run + timedelta(days=1)


def test_enqueue_due_every_other_day_post_moves_two_days(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    old_next_run = datetime.now(UTC) - timedelta(seconds=1)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        schedule_kind=ScheduleKind.every_other_day,
        next_run_at=old_next_run,
    )
    db_session.commit()

    scheduler.enqueue_due_posts()

    with SessionLocal() as db:
        refreshed = db.get(Post, post.id)
        assert as_aware(refreshed.next_run_at) == old_next_run + timedelta(days=2)


def test_next_run_for_weekdays_skips_weekend(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    friday = datetime(2026, 6, 19, 8, 30, tzinfo=UTC)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        schedule_kind=ScheduleKind.weekdays,
        next_run_at=friday,
    )

    next_run = scheduler.next_run_after(post, friday + timedelta(minutes=1))

    assert next_run == friday + timedelta(days=3)


def test_next_run_for_custom_weekdays_uses_selected_days(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    monday = datetime(2026, 6, 22, 8, 30, tzinfo=UTC)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        schedule_kind=ScheduleKind.custom_weekdays,
        next_run_at=monday,
    )
    post.schedule_weekdays = "2,4"

    next_run = scheduler.next_run_after(post, monday + timedelta(minutes=1))

    assert next_run == monday + timedelta(days=2)


def test_enqueue_ignores_future_paused_and_draft_posts(db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        status=PostStatus.scheduled,
        next_run_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        status=PostStatus.paused,
        next_run_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        status=PostStatus.draft,
        next_run_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    db_session.commit()

    created = scheduler.enqueue_due_posts()

    assert created == 0
    with SessionLocal() as db:
        assert db.query(PublishJob).count() == 0
