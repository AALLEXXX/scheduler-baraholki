from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from telethon.errors import FloodWaitError

from autopost_manager.alerts import send_alert
from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal
from autopost_manager.models import JobStatus, Post, PublishJob, SessionStatus, TelegramSession, UserSettings
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.send_errors import classify_send_error_info
from autopost_manager.telegram_client import send_post_from_session

PROCESSING_TIMEOUT_SECONDS = 10 * 60
MAX_JOB_ATTEMPTS = 3


async def alert_job_issue(
    job: PublishJob,
    *,
    action: str,
    status: str,
    error: str,
    session: TelegramSession | None = None,
) -> None:
    post = job.post
    chat = job.target_chat
    alert_session = session or job.session
    await send_alert(
        title="Publish job issue",
        status=status,
        fields={
            "action": action,
            "owner_telegram_id": post.created_by_telegram_id,
            "session_id": alert_session.id if alert_session else job.session_id,
            "session_status": alert_session.status.value if alert_session else None,
            "job_id": job.id,
            "post_id": post.id,
            "post_title": post.title,
            "target_chat_id": chat.id,
            "target_telegram_chat_id": chat.telegram_chat_id,
            "target_title": chat.title,
            "attempt": f"{job.attempts}/{MAX_JOB_ATTEMPTS}",
            "job_status": job.status.value,
            "next_attempt_at": job.next_attempt_at,
            "error": error,
        },
    )


def choose_session(db, job: PublishJob) -> TelegramSession | None:
    if job.session and job.session.status == SessionStatus.active:
        return job.session
    owner_id = job.post.created_by_telegram_id
    if owner_id is None:
        return None
    return db.scalars(
        select(TelegramSession)
        .where(TelegramSession.owner_telegram_id == owner_id)
        .where(TelegramSession.status == SessionStatus.active)
        .order_by(TelegramSession.last_send_at.asc().nullsfirst())
        .limit(1)
    ).first()


def owner_settings(db, owner_id: int | None) -> UserSettings | None:
    if owner_id is None:
        return None
    return db.get(UserSettings, owner_id)


def sent_today(db, owner_id: int | None) -> int:
    if owner_id is None:
        return 0
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.scalar(
            select(func.count())
            .select_from(PublishJob)
            .join(Post, PublishJob.post_id == Post.id)
            .where(Post.created_by_telegram_id == owner_id)
            .where(PublishJob.status == JobStatus.done)
            .where(PublishJob.updated_at >= today)
        )
        or 0
    )


def next_day_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def recover_stale_processing_jobs(db, now: datetime) -> int:
    return PublishJobRepository(db).recover_expired_processing_jobs(
        now,
        timeout_seconds=PROCESSING_TIMEOUT_SECONDS,
    )


def retry_delay(exc: Exception, attempts: int) -> timedelta | None:
    if attempts >= MAX_JOB_ATTEMPTS:
        return None
    if isinstance(exc, FloodWaitError):
        return timedelta(seconds=int(exc.seconds) + 30)
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError, OSError)):
        return timedelta(seconds=min(900, 60 * attempts))
    message = str(exc).lower()
    if "needs login" in message or "unauthorized" in message:
        return None
    if (
        "write forbidden" in message
        or "user is banned" in message
        or "not allowed to post" in message
        or "chatadminrequired" in message
        or "chat write forbidden" in message
    ):
        return None
    return timedelta(seconds=min(900, 60 * attempts))


async def process_one_job() -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        jobs = PublishJobRepository(db)
        jobs.recover_expired_processing_jobs(now, timeout_seconds=PROCESSING_TIMEOUT_SECONDS)
        job = jobs.claim_next_due_job(now, lease_seconds=PROCESSING_TIMEOUT_SECONDS)
        if not job:
            return False

        db.commit()
        db.refresh(job)

        session = choose_session(db, job)
        if not session:
            jobs.mark_failed(job, "No active session selected for job")
            db.commit()
            await alert_job_issue(job, action="send_post", status="failed", error=job.last_error)
            return True

        settings = owner_settings(db, job.post.created_by_telegram_id)
        if settings and settings.banned:
            jobs.mark_failed(job, "User is banned by administrator")
            db.commit()
            await alert_job_issue(job, action="send_post", status="failed", error=job.last_error, session=session)
            return True
        if settings and settings.autopost_paused:
            jobs.mark_cancelled(job, "Autoposting paused by user")
            db.commit()
            await alert_job_issue(job, action="send_post", status="cancelled", error=job.last_error, session=session)
            return True
        if settings and settings.daily_send_limit is not None:
            if sent_today(db, job.post.created_by_telegram_id) >= settings.daily_send_limit:
                jobs.mark_retry(job, "Daily send limit reached", next_day_start())
                db.commit()
                return True
        if job.post.media_items and len(job.post.media_items) > get_settings().max_media_items_per_post:
            jobs.mark_failed(job, "Too many media items")
            db.commit()
            await alert_job_issue(job, action="send_post", status="failed", error=job.last_error, session=session)
            return True

        try:
            message_id = await send_post_from_session(
                db=db,
                session=session,
                chat_id=job.target_chat.telegram_chat_id,
                post=job.post,
            )
        except Exception as exc:
            send_error = classify_send_error_info(exc)
            error = send_error.message
            if send_error.limited:
                session.status = SessionStatus.limited
            delay = retry_delay(exc, job.attempts)
            if delay is None or send_error.terminal:
                jobs.mark_failed(job, error)
            else:
                jobs.mark_retry(job, error, datetime.now(UTC) + delay)
            db.commit()
            await alert_job_issue(job, action="send_post", status=job.status.value, error=job.last_error, session=session)
            return True

        jobs.mark_done(job, message_id)
        db.commit()
        return True


async def run_worker() -> None:
    settings = get_settings()
    while True:
        processed = await process_one_job()
        if not processed:
            await asyncio.sleep(settings.worker_tick_seconds)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
