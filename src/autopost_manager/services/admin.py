from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autopost_manager.models import JobStatus, Post, PublishJob, TelegramSession, UserSettings
from autopost_manager.schemas import AdminStatsOut, AdminUserOut, AdminUserPageOut, AdminUserUpdate


def day_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    prefix = "+" if phone.startswith("+") else ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return f"{prefix}{'*' * len(digits)}"
    return f"{prefix}{digits[:2]}{'*' * max(3, len(digits) - 6)}{digits[-4:]}"


def sent_since(db: Session, *, telegram_user_id: int | None = None, since: datetime | None = None) -> int:
    query = select(func.count()).select_from(PublishJob).where(PublishJob.status == JobStatus.done)
    if telegram_user_id is not None:
        query = query.join(Post, PublishJob.post_id == Post.id).where(
            Post.created_by_telegram_id == telegram_user_id,
        )
    if since is not None:
        query = query.where(PublishJob.updated_at >= since)
    return int(db.scalar(query) or 0)


def failed_total(db: Session, *, telegram_user_id: int | None = None) -> int:
    query = select(func.count()).select_from(PublishJob).where(PublishJob.status == JobStatus.failed)
    if telegram_user_id is not None:
        query = query.join(Post, PublishJob.post_id == Post.id).where(
            Post.created_by_telegram_id == telegram_user_id,
        )
    return int(db.scalar(query) or 0)


@dataclass(slots=True)
class AdminService:
    db: Session

    def user_settings(self, telegram_user_id: int) -> UserSettings:
        settings = self.db.get(UserSettings, telegram_user_id)
        if settings:
            return settings
        settings = UserSettings(telegram_user_id=telegram_user_id)
        self.db.add(settings)
        self.db.flush()
        return settings

    def cancel_user_pending_jobs(self, telegram_user_id: int) -> int:
        jobs = list(
            self.db.scalars(
                select(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(Post.created_by_telegram_id == telegram_user_id)
                .where(PublishJob.status == JobStatus.pending)
            )
        )
        for job in jobs:
            job.status = JobStatus.cancelled
        return len(jobs)

    def admin_user_out(self, telegram_user_id: int) -> AdminUserOut:
        session = self.db.scalars(
            select(TelegramSession)
            .where(TelegramSession.owner_telegram_id == telegram_user_id)
            .order_by(TelegramSession.updated_at.desc())
        ).first()
        settings = self.db.get(UserSettings, telegram_user_id)
        return AdminUserOut(
            telegram_user_id=telegram_user_id,
            username=session.username if session else None,
            phone=mask_phone(session.phone if session else None),
            session_status=session.status if session else None,
            autopost_paused=bool(settings and settings.autopost_paused),
            banned=bool(settings and settings.banned),
            daily_send_limit=settings.daily_send_limit if settings else None,
            sent_today=sent_since(self.db, telegram_user_id=telegram_user_id, since=day_start()),
            failed_total=failed_total(self.db, telegram_user_id=telegram_user_id),
        )

    def list_users(self, *, page: int, page_size: int, query: str) -> AdminUserPageOut:
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

        start = (page - 1) * page_size
        page_owner_ids = owner_ids[start : start + page_size]
        return AdminUserPageOut(
            items=[self.admin_user_out(owner_id) for owner_id in page_owner_ids],
            page=page,
            page_size=page_size,
            total=len(owner_ids),
        )

    def update_user(self, telegram_user_id: int, payload: AdminUserUpdate) -> AdminUserOut:
        has_session = self.db.scalar(
            select(func.count())
            .select_from(TelegramSession)
            .where(TelegramSession.owner_telegram_id == telegram_user_id)
        )
        if not has_session and not self.db.get(UserSettings, telegram_user_id):
            raise HTTPException(status_code=404, detail="User not found")

        settings = self.user_settings(telegram_user_id)
        if payload.banned is not None:
            settings.banned = payload.banned
        if payload.autopost_paused is not None:
            settings.autopost_paused = payload.autopost_paused
            if payload.autopost_paused:
                self.cancel_user_pending_jobs(telegram_user_id)
        if "daily_send_limit" in payload.model_fields_set:
            settings.daily_send_limit = payload.daily_send_limit or None
        self.db.commit()
        return self.admin_user_out(telegram_user_id)

    def stats(self) -> AdminStatsOut:
        now = datetime.now(UTC)
        today = day_start()
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        users_total = int(
            self.db.scalar(
                select(func.count(func.distinct(TelegramSession.owner_telegram_id))).where(
                    TelegramSession.owner_telegram_id.is_not(None),
                )
            )
            or 0
        )
        daily_active_users = int(
            self.db.scalar(
                select(func.count(func.distinct(Post.created_by_telegram_id)))
                .select_from(PublishJob)
                .join(Post, PublishJob.post_id == Post.id)
                .where(PublishJob.status == JobStatus.done)
                .where(PublishJob.updated_at >= today)
                .where(Post.created_by_telegram_id.is_not(None))
            )
            or 0
        )
        return AdminStatsOut(
            sent_total=sent_since(self.db),
            sent_today=sent_since(self.db, since=today),
            sent_week=sent_since(self.db, since=week_start),
            sent_month=sent_since(self.db, since=month_start),
            failed_total=failed_total(self.db),
            users_total=users_total,
            daily_active_users=daily_active_users,
        )
