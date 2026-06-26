from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autopost_manager.models import JobStatus, Post, PublishJob, TelegramSession


class AdminRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def sent_since(
        self,
        *,
        telegram_user_id: int | None = None,
        since: datetime | None = None,
    ) -> int:
        query = select(func.count()).select_from(PublishJob).where(PublishJob.status == JobStatus.done)
        if telegram_user_id is not None:
            query = query.join(Post, PublishJob.post_id == Post.id).where(
                Post.created_by_telegram_id == telegram_user_id,
            )
        if since is not None:
            query = query.where(PublishJob.updated_at >= since)
        return int(self.db.scalar(query) or 0)

    def failed_total(self, *, telegram_user_id: int | None = None) -> int:
        query = select(func.count()).select_from(PublishJob).where(PublishJob.status == JobStatus.failed)
        if telegram_user_id is not None:
            query = query.join(Post, PublishJob.post_id == Post.id).where(
                Post.created_by_telegram_id == telegram_user_id,
            )
        return int(self.db.scalar(query) or 0)

    def user_count(self) -> int:
        return int(
            self.db.scalar(
                select(func.count(func.distinct(TelegramSession.owner_telegram_id))).where(
                    TelegramSession.owner_telegram_id.is_not(None),
                )
            )
            or 0
        )

    def daily_active_user_count(self, since: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count(func.distinct(Post.created_by_telegram_id)))
                .select_from(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(PublishJob.status == JobStatus.done)
                .where(PublishJob.updated_at >= since)
                .where(Post.created_by_telegram_id.is_not(None))
            )
            or 0
        )

    def list_owner_ids(self, *, query: str) -> list[int]:
        sessions = list(
            self.db.scalars(
                select(TelegramSession)
                .where(TelegramSession.owner_telegram_id.is_not(None))
                .order_by(TelegramSession.updated_at.desc())
            )
        )
        seen: set[int] = set()
        owner_ids: list[int] = []
        clean_query = query.strip().lower()
        for session in sessions:
            owner_id = int(session.owner_telegram_id)
            if owner_id in seen:
                continue
            searchable = " ".join(
                value
                for value in [
                    str(owner_id),
                    session.username or "",
                    session.phone or "",
                    session.name or "",
                ]
                if value
            ).lower()
            if clean_query and clean_query not in searchable:
                continue
            seen.add(owner_id)
            owner_ids.append(owner_id)
        return owner_ids
