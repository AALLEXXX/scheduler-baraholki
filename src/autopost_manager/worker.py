from __future__ import annotations

import asyncio

from autopost_manager.alerts import send_alert
from autopost_manager.consumers.worker import run_worker as consumer_run_worker
from autopost_manager.models import PublishJob, TelegramSession
from autopost_manager.services.worker import MAX_JOB_ATTEMPTS as MAX_JOB_ATTEMPTS
from autopost_manager.services.worker import PROCESSING_TIMEOUT_SECONDS as PROCESSING_TIMEOUT_SECONDS
from autopost_manager.services.worker import alert_job_issue as service_alert_job_issue
from autopost_manager.services.worker import choose_active_session_for_job as choose_active_session_for_job
from autopost_manager.services.worker import next_day_start as next_day_start
from autopost_manager.services.worker import owner_settings as owner_settings
from autopost_manager.services.worker import recover_stale_processing_jobs as recover_stale_processing_jobs
from autopost_manager.services.worker import retry_delay as retry_delay
from autopost_manager.services.worker import sent_today as sent_today
from autopost_manager.services.telegram_delivery import send_post_from_session

choose_session = choose_active_session_for_job


async def alert_job_issue(
    job: PublishJob,
    *,
    action: str,
    status: str,
    error: str,
    session: TelegramSession | None = None,
) -> None:
    await service_alert_job_issue(
        send_alert,
        job,
        action=action,
        status=status,
        error=error,
        session=session,
    )


async def process_one_job() -> bool:
    from autopost_manager.consumers.worker import process_one_job as consumer_process_one_job

    return await consumer_process_one_job(
        send_post=send_post_from_session,
        send_alert=send_alert,
        choose_active_session=choose_active_session_for_job,
    )


async def run_worker() -> None:
    await consumer_run_worker(process_job=process_one_job)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
