from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select
from telethon.errors import FloodWaitError

from autopost_manager.alerts import send_alert
from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal, create_schema
from autopost_manager.models import JobStatus, Post, PublishJob, SessionStatus, TelegramSession, UserSettings
from autopost_manager.telegram_client import classify_send_error, send_post_from_session

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
    stale_jobs = list(
        db.scalars(
            select(PublishJob)
            .where(PublishJob.status == JobStatus.processing)
            .where(
                (PublishJob.locked_until.is_not(None) & (PublishJob.locked_until < now))
                | (PublishJob.updated_at < now - timedelta(seconds=PROCESSING_TIMEOUT_SECONDS))
            )
        )
    )
    for job in stale_jobs:
        job.status = JobStatus.pending
        job.locked_until = None
        job.next_attempt_at = now
        job.last_error = "Recovered stale processing job"
    return len(stale_jobs)


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
    return timedelta(seconds=min(900, 60 * attempts))


async def process_one_job() -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        recover_stale_processing_jobs(db, now)
        blocked_owner_exists = exists().where(
            UserSettings.telegram_user_id == Post.created_by_telegram_id,
            (UserSettings.autopost_paused.is_(True)) | (UserSettings.banned.is_(True)),
        )
        job = db.scalars(
            select(PublishJob)
            .join(Post, PublishJob.post_id == Post.id)
            .where(PublishJob.status == JobStatus.pending)
            .where(PublishJob.due_at <= now)
            .where((PublishJob.next_attempt_at.is_(None)) | (PublishJob.next_attempt_at <= now))
            .where(~blocked_owner_exists)
            .order_by(PublishJob.due_at)
            .limit(1)
            .with_for_update(skip_locked=True, of=PublishJob)
        ).first()
        if not job:
            return False

        job.status = JobStatus.processing
        job.attempts += 1
        job.locked_until = now + timedelta(seconds=PROCESSING_TIMEOUT_SECONDS)
        job.next_attempt_at = None
        db.commit()
        db.refresh(job)

        session = choose_session(db, job)
        if not session:
            job.status = JobStatus.failed
            job.last_error = "No active session selected for job"
            job.locked_until = None
            db.commit()
            await alert_job_issue(job, action="send_post", status="failed", error=job.last_error)
            return True

        settings = owner_settings(db, job.post.created_by_telegram_id)
        if settings and settings.banned:
            job.status = JobStatus.failed
            job.last_error = "User is banned by administrator"
            job.locked_until = None
            db.commit()
            await alert_job_issue(job, action="send_post", status="failed", error=job.last_error, session=session)
            return True
        if settings and settings.autopost_paused:
            job.status = JobStatus.cancelled
            job.last_error = "Autoposting paused by user"
            job.locked_until = None
            db.commit()
            await alert_job_issue(job, action="send_post", status="cancelled", error=job.last_error, session=session)
            return True
        if settings and settings.daily_send_limit is not None:
            if sent_today(db, job.post.created_by_telegram_id) >= settings.daily_send_limit:
                job.status = JobStatus.pending
                job.last_error = "Daily send limit reached"
                job.locked_until = None
                job.next_attempt_at = next_day_start()
                db.commit()
                return True
        if job.post.media_items and len(job.post.media_items) > get_settings().max_media_items_per_post:
            job.status = JobStatus.failed
            job.last_error = "Too many media items"
            job.locked_until = None
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
            job.last_error = classify_send_error(exc, session)
            delay = retry_delay(exc, job.attempts)
            job.locked_until = None
            if delay is None:
                job.status = JobStatus.failed
                job.next_attempt_at = None
            else:
                job.status = JobStatus.pending
                job.next_attempt_at = datetime.now(UTC) + delay
            db.commit()
            await alert_job_issue(job, action="send_post", status=job.status.value, error=job.last_error, session=session)
            return True

        job.status = JobStatus.done
        job.telegram_message_id = message_id
        job.last_error = None
        job.locked_until = None
        job.next_attempt_at = None
        db.commit()
        return True


async def run_worker() -> None:
    create_schema()
    settings = get_settings()
    while True:
        processed = await process_one_job()
        if not processed:
            await asyncio.sleep(settings.worker_tick_seconds)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
