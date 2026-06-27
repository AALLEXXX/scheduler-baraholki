from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from autopost_manager.alerts import send_alert as default_send_alert
from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.models import TelegramSession
from autopost_manager.services.worker import WorkerService, choose_session
from autopost_manager.telegram_client import send_post_from_session

SendPost = Callable[..., Awaitable[int]]
SendAlert = Callable[..., Awaitable[None]]
ChooseSession = Callable[..., TelegramSession | None]


async def process_one_job(
    *,
    send_post: SendPost = send_post_from_session,
    send_alert: SendAlert = default_send_alert,
    choose_active_session: ChooseSession = choose_session,
) -> bool:
    with SessionLocal() as db:
        service = WorkerService(
            db=db,
            settings=get_settings(),
            send_post=send_post,
            send_alert=send_alert,
            choose_session=choose_active_session,
        )
        return await service.process_one_job()


async def run_worker(
    *,
    process_job: Callable[[], Awaitable[bool]] | None = None,
) -> None:
    settings = get_settings()
    process = process_job or (lambda: process_one_job())
    while True:
        processed = await process()
        if not processed:
            await asyncio.sleep(settings.worker_tick_seconds)


def main() -> None:
    asyncio.run(run_worker())
