from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.models import Post, PostStatus, ScheduleKind
from autopost_manager.repositories.posts import PostRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
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
        return advance_by_days_until_future(current, now, 1, timezone_name=post.timezone)
    if post.schedule_kind == ScheduleKind.weekly:
        return advance_by_days_until_future(current, now, 7, timezone_name=post.timezone)
    if post.schedule_kind == ScheduleKind.every_other_day:
        return advance_by_days_until_future(current, now, 2, timezone_name=post.timezone)
    if post.schedule_kind == ScheduleKind.weekdays:
        return next_same_time_on_weekdays(
            current,
            now,
            WeekdaySet(frozenset({0, 1, 2, 3, 4})),
            timezone_name=post.timezone,
        )
    if post.schedule_kind == ScheduleKind.weekends:
        return next_same_time_on_weekdays(
            current,
            now,
            WeekdaySet(frozenset({5, 6})),
            timezone_name=post.timezone,
        )
    if post.schedule_kind == ScheduleKind.custom_weekdays:
        return next_same_time_on_weekdays(
            current,
            now,
            WeekdaySet.parse_storage_value(post.schedule_weekdays),
            timezone_name=post.timezone,
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
            posts = PostRepository(db)
            jobs = PublishJobRepository(db)

            for post in posts.list_due_scheduled_unblocked(current_time):
                if len({target.target_chat_id for target in post.targets}) > get_settings().max_targets_per_post:
                    post.status = PostStatus.paused
                    continue
                owner_id = post.created_by_telegram_id
                if owner_id is not None:
                    today_jobs = jobs.count_created_since_for_owner(
                        owner_telegram_id=owner_id,
                        since=day_start,
                    )
                    if today_jobs >= get_settings().max_jobs_per_user_per_day:
                        post.next_run_at = current_time + timedelta(hours=1)
                        continue
                for target in post.targets:
                    if jobs.active_for_post_target(
                        post_id=post.id,
                        target_chat_id=target.target_chat_id,
                    ):
                        continue
                    jobs.add_pending(
                        post_id=post.id,
                        target_chat_id=target.target_chat_id,
                        session_id=post.default_session_id,
                        due_at=current_time,
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
