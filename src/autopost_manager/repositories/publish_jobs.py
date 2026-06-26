from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, joinedload

from autopost_manager.models import JobStatus, Post, PublishJob, UserSettings


class PublishJobRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def recover_expired_processing_jobs(self, now: datetime, *, timeout_seconds: int) -> int:
        stale_jobs = list(
            self.db.scalars(
                select(PublishJob)
                .where(PublishJob.status == JobStatus.processing)
                .where(
                    (PublishJob.locked_until.is_not(None) & (PublishJob.locked_until < now))
                    | (PublishJob.updated_at < now - timedelta(seconds=timeout_seconds))
                )
            )
        )
        for job in stale_jobs:
            job.status = JobStatus.pending
            job.locked_until = None
            job.next_attempt_at = now
            job.last_error = "Recovered stale processing job"
        return len(stale_jobs)

    def claim_next_due_job(self, now: datetime, *, lease_seconds: int) -> PublishJob | None:
        blocked_owner_exists = exists().where(
            UserSettings.telegram_user_id == Post.created_by_telegram_id,
            (UserSettings.autopost_paused.is_(True)) | (UserSettings.banned.is_(True)),
        )
        job = self.db.scalars(
            select(PublishJob)
            .options(
                joinedload(PublishJob.post),
                joinedload(PublishJob.target_chat),
                joinedload(PublishJob.session),
            )
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
            return None

        job.status = JobStatus.processing
        job.attempts += 1
        job.locked_until = now + timedelta(seconds=lease_seconds)
        job.next_attempt_at = None
        return job

    def mark_done(self, job: PublishJob, telegram_message_id: int) -> None:
        job.status = JobStatus.done
        job.telegram_message_id = telegram_message_id
        job.last_error = None
        job.locked_until = None
        job.next_attempt_at = None

    def mark_failed(self, job: PublishJob, error: str) -> None:
        job.status = JobStatus.failed
        job.last_error = error
        job.locked_until = None
        job.next_attempt_at = None

    def mark_cancelled(self, job: PublishJob, error: str) -> None:
        job.status = JobStatus.cancelled
        job.last_error = error
        job.locked_until = None

    def mark_retry(self, job: PublishJob, error: str, next_attempt_at: datetime) -> None:
        job.status = JobStatus.pending
        job.last_error = error
        job.locked_until = None
        job.next_attempt_at = next_attempt_at
