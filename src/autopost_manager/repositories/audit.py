from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autopost_manager.models import Post, PublishJob, TargetChat


@dataclass(frozen=True, slots=True)
class AuditJobRow:
    job: PublishJob
    post: Post
    chat: TargetChat


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def count_for_owner(self, telegram_user_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(Post.created_by_telegram_id == telegram_user_id)
            )
            or 0
        )

    def list_for_owner(self, *, telegram_user_id: int, page: int, page_size: int) -> list[AuditJobRow]:
        rows = self.db.execute(
            select(PublishJob, Post, TargetChat)
            .join(Post, PublishJob.post_id == Post.id)
            .join(TargetChat, PublishJob.target_chat_id == TargetChat.id)
            .where(Post.created_by_telegram_id == telegram_user_id)
            .order_by(PublishJob.updated_at.desc(), PublishJob.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return [AuditJobRow(job=job, post=post, chat=chat) for job, post, chat in rows]

    def fetch_for_owner(self, *, telegram_user_id: int, job_id: uuid.UUID) -> AuditJobRow | None:
        row = self.db.execute(
            select(PublishJob, Post, TargetChat)
            .join(Post, PublishJob.post_id == Post.id)
            .join(TargetChat, PublishJob.target_chat_id == TargetChat.id)
            .where(PublishJob.id == job_id)
            .where(Post.created_by_telegram_id == telegram_user_id)
        ).first()
        if not row:
            return None
        job, post, chat = row
        return AuditJobRow(job=job, post=post, chat=chat)
