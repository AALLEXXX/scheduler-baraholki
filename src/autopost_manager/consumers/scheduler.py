from __future__ import annotations

import asyncio

from autopost_manager.config import get_settings
from autopost_manager.services.scheduler import SchedulerService


def enqueue_due_posts() -> int:
    return SchedulerService().enqueue_due_posts()


async def run_scheduler() -> None:
    settings = get_settings()
    while True:
        enqueue_due_posts()
        await asyncio.sleep(settings.scheduler_tick_seconds)


def main() -> None:
    asyncio.run(run_scheduler())
