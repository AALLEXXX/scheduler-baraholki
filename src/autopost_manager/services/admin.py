from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from autopost_manager.models import UserSettings
from autopost_manager.repositories.admin import AdminRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.user_settings import UserSettingsRepository
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
    return AdminRepository(db).sent_since(telegram_user_id=telegram_user_id, since=since)


def failed_total(db: Session, *, telegram_user_id: int | None = None) -> int:
    return AdminRepository(db).failed_total(telegram_user_id=telegram_user_id)


@dataclass(slots=True)
class AdminService:
    db: Session

    def user_settings(self, telegram_user_id: int) -> UserSettings:
        return UserSettingsRepository(self.db).get_or_create(telegram_user_id)

    def cancel_user_pending_jobs(self, telegram_user_id: int) -> int:
        return PublishJobRepository(self.db).cancel_pending_for_owner(telegram_user_id)

    def admin_user_out(self, telegram_user_id: int) -> AdminUserOut:
        session = TelegramSessionRepository(self.db).latest_for_owner(telegram_user_id)
        settings = UserSettingsRepository(self.db).fetch_by_user_id(telegram_user_id)
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
        owner_ids = AdminRepository(self.db).list_owner_ids(query=query)
        start = (page - 1) * page_size
        page_owner_ids = owner_ids[start : start + page_size]
        return AdminUserPageOut(
            items=[self.admin_user_out(owner_id) for owner_id in page_owner_ids],
            page=page,
            page_size=page_size,
            total=len(owner_ids),
        )

    def update_user(self, telegram_user_id: int, payload: AdminUserUpdate) -> AdminUserOut:
        session_repository = TelegramSessionRepository(self.db)
        settings_repository = UserSettingsRepository(self.db)
        if not session_repository.count_for_owner(telegram_user_id) and not settings_repository.fetch_by_user_id(
            telegram_user_id,
        ):
            raise HTTPException(status_code=404, detail="User not found")

        settings = settings_repository.get_or_create(telegram_user_id)
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
        admin_repository = AdminRepository(self.db)
        return AdminStatsOut(
            sent_total=admin_repository.sent_since(),
            sent_today=admin_repository.sent_since(since=today),
            sent_week=admin_repository.sent_since(since=week_start),
            sent_month=admin_repository.sent_since(since=month_start),
            failed_total=admin_repository.failed_total(),
            users_total=admin_repository.user_count(),
            daily_active_users=admin_repository.daily_active_user_count(today),
        )
