from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.models import JobStatus, Post, PostStatus, PublishJob, ScheduleKind, UserSettings
from autopost_manager.schedule import (
    WeekdaySet,
    advance_by_days_until_future,
    as_utc_aware,
    next_same_time_on_weekdays,
)


def next_run_after(post: Post, now: datetime) -> datetime | None:
    current = as_utc_aware(post.next_run_at or now)

    if post.schedule_kind == ScheduleKind.interval and post.interval_minutes:
        return now + timedelta(minutes=post.interval_minutes)
    if post.schedule_kind == ScheduleKind.daily:
        return advance_by_days_until_future(current, now, 1)
    if post.schedule_kind == ScheduleKind.weekly:
        return advance_by_days_until_future(current, now, 7)
    if post.schedule_kind == ScheduleKind.every_other_day:
        return advance_by_days_until_future(current, now, 2)
    if post.schedule_kind == ScheduleKind.weekdays:
        return next_same_time_on_weekdays(current, now, WeekdaySet(frozenset({0, 1, 2, 3, 4})))
    if post.schedule_kind == ScheduleKind.weekends:
        return next_same_time_on_weekdays(current, now, WeekdaySet(frozenset({5, 6})))
    if post.schedule_kind == ScheduleKind.custom_weekdays:
        return next_same_time_on_weekdays(
            current,
            now,
            WeekdaySet.parse_storage_value(post.schedule_weekdays),
        )
    return None


class SchedulerService:
    def __init__(self, db_factory: Callable[[], Session] = SessionLocal) -> None:
        self.db_factory = db_factory

    def enqueue_due_posts(self, now: datetime | None = None) -> int:
        current_time = now or datetime.now(UTC)
        day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        created = 0
        with self.db_factory() as db:
            blocked_owner_exists = exists().where(
                UserSettings.telegram_user_id == Post.created_by_telegram_id,
                (UserSettings.autopost_paused.is_(True)) | (UserSettings.banned.is_(True)),
            )
            posts = db.scalars(
                select(Post)
                .where(Post.status == PostStatus.scheduled)
                .where(Post.next_run_at.is_not(None))
                .where(Post.next_run_at <= current_time)
                .where(~blocked_owner_exists)
                .with_for_update(skip_locked=True, of=Post)
            ).unique()

            for post in posts:
                if len({target.target_chat_id for target in post.targets}) > get_settings().max_targets_per_post:
                    post.status = PostStatus.paused
                    continue
                owner_id = post.created_by_telegram_id
                if owner_id is not None:
                    today_jobs = int(
                        db.scalar(
                            select(func.count())
                            .select_from(PublishJob)
                            .join(Post, PublishJob.post_id == Post.id)
                            .where(Post.created_by_telegram_id == owner_id)
                            .where(PublishJob.created_at >= day_start)
                        )
                        or 0
                    )
                    if today_jobs >= get_settings().max_jobs_per_user_per_day:
                        post.next_run_at = current_time + timedelta(hours=1)
                        continue
                for target in post.targets:
                    existing = db.scalars(
                        select(PublishJob)
                        .where(PublishJob.post_id == post.id)
                        .where(PublishJob.target_chat_id == target.target_chat_id)
                        .where(PublishJob.status.in_([JobStatus.pending, JobStatus.processing]))
                    ).first()
                    if existing:
                        continue
                    db.add(
                        PublishJob(
                            post_id=post.id,
                            target_chat_id=target.target_chat_id,
                            session_id=post.default_session_id,
                            due_at=current_time,
                        )
                    )
                    created += 1

                if post.schedule_kind == ScheduleKind.once:
                    post.status = PostStatus.archived
                else:
                    post.next_run_at = next_run_after(post, current_time)
                    if not post.next_run_at:
                        post.status = PostStatus.paused
            db.commit()
        return created
