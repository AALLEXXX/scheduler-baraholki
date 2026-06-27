from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import exists, func, select
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

    def cancel_pending_for_post(self, post_id: UUID) -> int:
        jobs = list(
            self.db.scalars(
                select(PublishJob)
                .where(PublishJob.post_id == post_id)
                .where(PublishJob.status == JobStatus.pending)
            )
        )
        for job in jobs:
            job.status = JobStatus.cancelled
        return len(jobs)

    def cancel_pending_for_owner(self, owner_telegram_id: int) -> int:
        jobs = list(
            self.db.scalars(
                select(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .where(PublishJob.status == JobStatus.pending)
            )
        )
        for job in jobs:
            job.status = JobStatus.cancelled
        return len(jobs)

    def list_for_post(self, post_id: UUID) -> list[PublishJob]:
        return list(self.db.scalars(select(PublishJob).where(PublishJob.post_id == post_id)))

    def list_recent_for_owner(self, owner_telegram_id: int, *, limit: int) -> list[PublishJob]:
        return list(
            self.db.scalars(
                select(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .order_by(PublishJob.created_at.desc())
                .limit(limit)
            )
        )

    def delete_for_post(self, post_id: UUID) -> int:
        jobs = self.list_for_post(post_id)
        for job in jobs:
            self.db.delete(job)
        return len(jobs)

    def active_for_post_target(self, *, post_id: UUID, target_chat_id: UUID) -> PublishJob | None:
        return self.db.scalars(
            select(PublishJob)
            .where(PublishJob.post_id == post_id)
            .where(PublishJob.target_chat_id == target_chat_id)
            .where(PublishJob.status.in_([JobStatus.pending, JobStatus.processing]))
        ).first()

    def add_pending(
        self,
        *,
        post_id: UUID,
        target_chat_id: UUID,
        session_id: UUID | None,
        due_at: datetime,
    ) -> PublishJob:
        job = PublishJob(
            post_id=post_id,
            target_chat_id=target_chat_id,
            session_id=session_id,
            due_at=due_at,
        )
        self.db.add(job)
        return job

    def count_created_since_for_owner(self, *, owner_telegram_id: int, since: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .where(PublishJob.created_at >= since)
            )
            or 0
        )

    def count_done_since_for_owner(self, *, owner_telegram_id: int, since: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .where(PublishJob.status == JobStatus.done)
                .where(PublishJob.updated_at >= since)
            )
            or 0
        )
