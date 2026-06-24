from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import exists, select

from autopost_manager.config import get_settings
from autopost_manager.db import SessionLocal, create_schema
from autopost_manager.models import JobStatus, Post, PublishJob, SessionStatus, TelegramSession, UserSettings
from autopost_manager.telegram_client import classify_send_error, send_post_from_session


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


def owner_autopost_paused(db, owner_id: int | None) -> bool:
    if owner_id is None:
        return False
    return (
        db.scalar(
            select(UserSettings.autopost_paused).where(
                UserSettings.telegram_user_id == owner_id,
            )
        )
        is True
    )


async def process_one_job() -> bool:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        paused_owner_exists = exists().where(
            UserSettings.telegram_user_id == Post.created_by_telegram_id,
            UserSettings.autopost_paused.is_(True),
        )
        job = db.scalars(
            select(PublishJob)
            .join(Post, PublishJob.post_id == Post.id)
            .where(PublishJob.status == JobStatus.pending)
            .where(PublishJob.due_at <= now)
            .where(~paused_owner_exists)
            .order_by(PublishJob.due_at)
            .limit(1)
            .with_for_update(skip_locked=True, of=PublishJob)
        ).first()
        if not job:
            return False

        job.status = JobStatus.processing
        job.attempts += 1
        db.commit()
        db.refresh(job)

        session = choose_session(db, job)
        if not session:
            job.status = JobStatus.failed
            job.last_error = "No active session selected for job"
            db.commit()
            return True

        if owner_autopost_paused(db, job.post.created_by_telegram_id):
            job.status = JobStatus.cancelled
            job.last_error = "Autoposting paused by user"
            db.commit()
            return True

        try:
            message_id = await send_post_from_session(
                db=db,
                session=session,
                chat_id=job.target_chat.telegram_chat_id,
                post=job.post,
            )
        except Exception as exc:
            job.status = JobStatus.failed
            job.last_error = classify_send_error(exc, session)
            db.commit()
            return True

        job.status = JobStatus.done
        job.telegram_message_id = message_id
        job.last_error = None
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
