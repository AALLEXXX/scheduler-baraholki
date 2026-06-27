from __future__ import annotations

import asyncio
from datetime import datetime

from autopost_manager.consumers.scheduler import enqueue_due_posts as consumer_enqueue_due_posts
from autopost_manager.consumers.scheduler import run_scheduler as consumer_run_scheduler
from autopost_manager.models import Post
from autopost_manager.schedule import as_utc_aware
from autopost_manager.services.scheduler import next_run_after as calculate_next_run_after


def as_aware(value: datetime) -> datetime:
    return as_utc_aware(value)


def next_run_after(post: Post, now: datetime) -> datetime | None:
    return calculate_next_run_after(post, now)


def enqueue_due_posts() -> int:
    return consumer_enqueue_due_posts()


async def run_scheduler() -> None:
    await consumer_run_scheduler()


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
