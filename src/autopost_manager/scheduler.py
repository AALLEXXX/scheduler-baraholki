from __future__ import annotations

import asyncio
from datetime import datetime

from autopost_manager.config import get_settings
from autopost_manager.models import Post
from autopost_manager.schedule import as_utc_aware
from autopost_manager.services.scheduler import SchedulerService
from autopost_manager.services.scheduler import next_run_after as calculate_next_run_after


def as_aware(value: datetime) -> datetime:
    return as_utc_aware(value)


def next_run_after(post: Post, now: datetime) -> datetime | None:
    return calculate_next_run_after(post, now)


def enqueue_due_posts() -> int:
    return SchedulerService().enqueue_due_posts()


async def run_scheduler() -> None:
    settings = get_settings()
    while True:
        enqueue_due_posts()
        await asyncio.sleep(settings.scheduler_tick_seconds)


def main() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
