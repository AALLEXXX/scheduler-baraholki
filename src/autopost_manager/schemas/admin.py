from __future__ import annotations

from pydantic import BaseModel, Field

from autopost_manager.models import SessionStatus


class AdminUserOut(BaseModel):
    telegram_user_id: int
    username: str | None = None
    phone: str | None = None
    session_status: SessionStatus | None = None
    autopost_paused: bool = False
    banned: bool = False
    daily_send_limit: int | None = None
    sent_today: int = 0
    failed_total: int = 0


class AdminUserPageOut(BaseModel):
    items: list[AdminUserOut]
    page: int
    page_size: int
    total: int


class AdminUserUpdate(BaseModel):
    banned: bool | None = None
    autopost_paused: bool | None = None
    daily_send_limit: int | None = Field(default=None, ge=0)


class AdminStatsOut(BaseModel):
    sent_total: int
    sent_today: int
    sent_week: int
    sent_month: int
    failed_total: int
    users_total: int
    daily_active_users: int
