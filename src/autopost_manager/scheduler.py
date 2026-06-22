from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal, create_schema
from autopost_manager.models import Post, PostStatus, PublishJob, ScheduleKind


def enqueue_due_posts() -> int:
    now = datetime.now(UTC)
    created = 0
    with SessionLocal() as db:
        posts = db.scalars(
            select(Post)
            .where(Post.status == PostStatus.scheduled)
            .where(Post.next_run_at.is_not(None))
            .where(Post.next_run_at <= now)
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
            elif post.schedule_kind == ScheduleKind.interval and post.interval_minutes:
                post.next_run_at = now + timedelta(minutes=post.interval_minutes)
            else:
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
