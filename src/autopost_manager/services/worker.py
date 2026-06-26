from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from telethon.errors import FloodWaitError

from autopost_manager.config import Settings
from autopost_manager.models import JobStatus, Post, PublishJob, SessionStatus, TelegramSession, UserSettings
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.user_settings import UserSettingsRepository
from autopost_manager.send_errors import classify_send_error_info

PROCESSING_TIMEOUT_SECONDS = 10 * 60
MAX_JOB_ATTEMPTS = 3

SendPost = Callable[..., Awaitable[int]]
SendAlert = Callable[..., Awaitable[None]]
ChooseSession = Callable[[Session, PublishJob], TelegramSession | None]


async def alert_job_issue(
    alert_func: SendAlert,
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
    await alert_func(
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


def choose_session(db: Session, job: PublishJob) -> TelegramSession | None:
    if job.session and job.session.status == SessionStatus.active:
        return job.session
    owner_id = job.post.created_by_telegram_id
    if owner_id is None:
        return None
    return TelegramSessionRepository(db).least_recently_used_active_for_owner(owner_id)


def owner_settings(db: Session, owner_id: int | None) -> UserSettings | None:
    if owner_id is None:
        return None
    return UserSettingsRepository(db).fetch_by_user_id(owner_id)


def sent_today(db: Session, owner_id: int | None) -> int:
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


def recover_stale_processing_jobs(db: Session, now: datetime) -> int:
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


@dataclass(slots=True)
class WorkerService:
    db: Session
    settings: Settings
    send_post: SendPost
    send_alert: SendAlert
    choose_session: ChooseSession

    async def process_one_job(self) -> bool:
        now = datetime.now(UTC)
        jobs = PublishJobRepository(self.db)
        jobs.recover_expired_processing_jobs(now, timeout_seconds=PROCESSING_TIMEOUT_SECONDS)
        job = jobs.claim_next_due_job(now, lease_seconds=PROCESSING_TIMEOUT_SECONDS)
        if not job:
            return False

        self.db.commit()
        self.db.refresh(job)

        session = self.choose_session(self.db, job)
        if not session:
            jobs.mark_failed(job, "No active session selected for job")
            self.db.commit()
            await self._alert_job_issue(job, action="send_post", status="failed", error=job.last_error)
            return True

        settings = owner_settings(self.db, job.post.created_by_telegram_id)
        if settings and settings.banned:
            jobs.mark_failed(job, "User is banned by administrator")
            self.db.commit()
            await self._alert_job_issue(
                job,
                action="send_post",
                status="failed",
                error=job.last_error,
                session=session,
            )
            return True
        if settings and settings.autopost_paused:
            jobs.mark_cancelled(job, "Autoposting paused by user")
            self.db.commit()
            await self._alert_job_issue(
                job,
                action="send_post",
                status="cancelled",
                error=job.last_error,
                session=session,
            )
            return True
        if settings and settings.daily_send_limit is not None:
            if sent_today(self.db, job.post.created_by_telegram_id) >= settings.daily_send_limit:
                jobs.mark_retry(job, "Daily send limit reached", next_day_start())
                self.db.commit()
                return True
        if job.post.media_items and len(job.post.media_items) > self.settings.max_media_items_per_post:
            jobs.mark_failed(job, "Too many media items")
            self.db.commit()
            await self._alert_job_issue(job, action="send_post", status="failed", error=job.last_error, session=session)
            return True

        try:
            message_id = await self.send_post(
                db=self.db,
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
            self.db.commit()
            await self._alert_job_issue(
                job,
                action="send_post",
                status=job.status.value,
                error=job.last_error,
                session=session,
            )
            return True

        jobs.mark_done(job, message_id)
        self.db.commit()
        return True

    async def _alert_job_issue(
        self,
        job: PublishJob,
        *,
        action: str,
        status: str,
        error: str,
        session: TelegramSession | None = None,
    ) -> None:
        await alert_job_issue(
            self.send_alert,
            job,
            action=action,
            status=status,
            error=error,
            session=session,
        )
