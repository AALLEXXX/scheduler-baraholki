from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal, create_schema
from autopost_manager.models import Post, PostStatus, PublishJob, ScheduleKind, UserSettings


def as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def parse_weekdays(value: str | None) -> set[int]:
    if not value:
        return set()
    days: set[int] = set()
    for item in value.split(","):
        try:
            day = int(item)
        except ValueError:
            continue
        if 0 <= day <= 6:
            days.add(day)
    return days


def advance_by_days_until_future(start: datetime, now: datetime, days: int) -> datetime:
    candidate = as_aware(start)
    reference = as_aware(now)
    while candidate <= reference:
        candidate += timedelta(days=days)
    return candidate


def next_same_time_on_weekdays(start: datetime, now: datetime, weekdays: set[int]) -> datetime | None:
    if not weekdays:
        return None
    candidate = as_aware(start)
    reference = as_aware(now)
    for _ in range(15):
        candidate += timedelta(days=1)
        if candidate > reference and candidate.weekday() in weekdays:
            return candidate
    return None


def next_run_after(post: Post, now: datetime) -> datetime | None:
    current = as_aware(post.next_run_at or now)

    if post.schedule_kind == ScheduleKind.interval and post.interval_minutes:
        return now + timedelta(minutes=post.interval_minutes)
    if post.schedule_kind == ScheduleKind.daily:
        return advance_by_days_until_future(current, now, 1)
    if post.schedule_kind == ScheduleKind.weekly:
        return advance_by_days_until_future(current, now, 7)
    if post.schedule_kind == ScheduleKind.every_other_day:
        return advance_by_days_until_future(current, now, 2)
    if post.schedule_kind == ScheduleKind.weekdays:
        return next_same_time_on_weekdays(current, now, {0, 1, 2, 3, 4})
    if post.schedule_kind == ScheduleKind.weekends:
        return next_same_time_on_weekdays(current, now, {5, 6})
    if post.schedule_kind == ScheduleKind.custom_weekdays:
        return next_same_time_on_weekdays(current, now, parse_weekdays(post.schedule_weekdays))
    return None


def enqueue_due_posts() -> int:
    now = datetime.now(UTC)
    created = 0
    with SessionLocal() as db:
        posts = db.scalars(
            select(Post)
            .outerjoin(UserSettings, UserSettings.telegram_user_id == Post.created_by_telegram_id)
            .where(Post.status == PostStatus.scheduled)
            .where(Post.next_run_at.is_not(None))
            .where(Post.next_run_at <= now)
            .where(or_(UserSettings.telegram_user_id.is_(None), UserSettings.autopost_paused.is_(False)))
        ).unique()

        for post in posts:
            for target in post.targets:
                db.add(
                    PublishJob(
                        post_id=post.id,
                        target_chat_id=target.target_chat_id,
                        session_id=post.default_session_id,
                        due_at=now,
                    )
                )
                created += 1

            if post.schedule_kind == ScheduleKind.once:
                post.status = PostStatus.archived
            else:
                post.next_run_at = next_run_after(post, now)
                if not post.next_run_at:
                    post.status = PostStatus.paused
        db.commit()
    return created


async def run_scheduler() -> None:
    create_schema()
    settings = get_settings()
    while True:
        enqueue_due_posts()
        await asyncio.sleep(settings.scheduler_tick_seconds)


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
