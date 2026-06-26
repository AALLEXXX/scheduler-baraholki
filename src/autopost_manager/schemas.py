from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
import uuid

from pydantic import BaseModel, Field, field_validator

from autopost_manager.models import JobStatus, PostStatus, ScheduleKind, SessionStatus, TargetChatType

MAX_TARGET_CHAT_IDS = 15
MAX_SCHEDULE_WEEKDAYS = 7
ParseMode = Literal["html"]
SessionStrategy = Literal["fixed"]


def normalize_schedule_weekdays(values: list[int]) -> list[int]:
    invalid = [value for value in values if value < 0 or value > 6]
    if invalid:
        raise ValueError("Дни недели должны быть числами от 0 до 6")
    return sorted(set(values))


def ensure_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Укажите корректную IANA timezone") from exc
    return value


class TelegramSessionOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    telegram_user_id: int | None
    username: str | None
    status: SessionStatus
    min_send_interval_seconds: int

    model_config = {"from_attributes": True}


class AppConfigOut(BaseModel):
    bot_username: str
    is_admin: bool = False


class UserSettingsOut(BaseModel):
    autopost_paused: bool = False


class AccountStartLogin(BaseModel):
    phone: str = Field(min_length=1, max_length=40)
    force_sms: bool = False

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        cleaned = re.sub(r"[\s().-]", "", value.strip())
        if cleaned.startswith("00"):
            cleaned = f"+{cleaned[2:]}"
        if not cleaned.startswith("+"):
            raise ValueError("Выберите код страны и введите номер в международном формате")
        digits = cleaned[1:]
        if not digits.isdigit() or not 8 <= len(digits) <= 15:
            raise ValueError("Проверьте номер телефона: нужен код страны и 8-15 цифр")
        return cleaned


class AccountCodeConfirm(BaseModel):
    session_id: uuid.UUID
    code: str = Field(min_length=3, max_length=20)


class AccountPasswordConfirm(BaseModel):
    session_id: uuid.UUID
    password: str = Field(min_length=1, max_length=300)


class AccountLoginOut(BaseModel):
    session_id: uuid.UUID
    status: SessionStatus
    message: str
    delivery_type: str | None = None
    next_delivery_type: str | None = None


class TargetChatCreate(BaseModel):
    session_id: uuid.UUID | None = None
    telegram_chat_id: int
    title: str
    username: str | None = None
    type: TargetChatType = TargetChatType.supergroup
    enabled: bool = True


class TargetChatOut(TargetChatCreate):
    id: uuid.UUID

    model_config = {"from_attributes": True}


class DialogFolderOut(BaseModel):
    id: int
    title: str
    telegram_chat_ids: list[int] = Field(default_factory=list)


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4096)
    parse_mode: ParseMode | None = "html"
    status: PostStatus = PostStatus.draft
    schedule_kind: ScheduleKind = ScheduleKind.once
    next_run_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    schedule_weekdays: list[int] = Field(default_factory=list, max_length=MAX_SCHEDULE_WEEKDAYS)
    timezone: str = "Asia/Tbilisi"
    session_strategy: SessionStrategy = "fixed"
    default_session_id: uuid.UUID | None = None
    target_chat_ids: list[uuid.UUID] = Field(default_factory=list)
    spam_risk_acknowledged: bool = False

    @field_validator("schedule_weekdays")
    @classmethod
    def validate_schedule_weekdays(cls, values: list[int]) -> list[int]:
        return normalize_schedule_weekdays(values)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return ensure_timezone(value)

    @field_validator("target_chat_ids")
    @classmethod
    def validate_target_chat_ids(cls, values: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(values)) > MAX_TARGET_CHAT_IDS:
            raise ValueError(f"Можно выбрать не больше {MAX_TARGET_CHAT_IDS} групп на один пост")
        return values


class PostScheduleUpdate(BaseModel):
    schedule_kind: ScheduleKind = ScheduleKind.once
    next_run_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    schedule_weekdays: list[int] = Field(default_factory=list, max_length=MAX_SCHEDULE_WEEKDAYS)
    timezone: str = "Asia/Tbilisi"
    default_session_id: uuid.UUID
    target_chat_ids: list[uuid.UUID] = Field(default_factory=list)
    spam_risk_acknowledged: bool = False

    @field_validator("schedule_weekdays")
    @classmethod
    def validate_schedule_weekdays(cls, values: list[int]) -> list[int]:
        return normalize_schedule_weekdays(values)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return ensure_timezone(value)

    @field_validator("target_chat_ids")
    @classmethod
    def validate_target_chat_ids(cls, values: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(values)) > MAX_TARGET_CHAT_IDS:
            raise ValueError(f"Можно выбрать не больше {MAX_TARGET_CHAT_IDS} групп на один пост")
        return values


class PostResumeUpdate(BaseModel):
    next_run_at: datetime | None = None


class ChatSyncResult(BaseModel):
    imported: int
    total_dialogs: int


class AccountPauseOut(BaseModel):
    autopost_paused: bool
    cancelled_jobs: int = 0


class AccountRevokeOut(BaseModel):
    revoked_sessions: int
    disabled_chats: int
    cancelled_jobs: int
    telegram_logout_errors: list[str] = Field(default_factory=list)


class DeletePostOut(BaseModel):
    ok: bool
    deleted_jobs: int
    source_messages_found: int
    telegram_delete_attempted: int
    deleted_bot_messages: int
    telegram_delete_errors: list[str] = Field(default_factory=list)


class PostMediaOut(BaseModel):
    id: uuid.UUID
    media_type: str
    file_id: str
    file_unique_id: str | None
    order_index: int

    model_config = {"from_attributes": True}


class PostOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    parse_mode: ParseMode | None
    status: PostStatus
    schedule_kind: ScheduleKind
    next_run_at: datetime | None
    interval_minutes: int | None
    schedule_weekdays: list[int] = Field(default_factory=list)
    timezone: str
    session_strategy: SessionStrategy
    default_session_id: uuid.UUID | None
    target_chat_ids: list[uuid.UUID]
    media: list[PostMediaOut] = Field(default_factory=list)


class JobOut(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    target_chat_id: uuid.UUID
    session_id: uuid.UUID | None
    due_at: datetime
    status: JobStatus
    attempts: int
    last_error: str | None
    telegram_message_id: int | None

    model_config = {"from_attributes": True}


class AuditItemOut(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    post_title: str
    post_preview: str
    media_count: int
    target_chat_id: uuid.UUID
    target_chat_title: str
    due_at: datetime
    updated_at: datetime
    status: JobStatus
    attempts: int
    telegram_message_id: int | None
    message_link: str | None = None
    last_error: str | None


class AuditPageOut(BaseModel):
    items: list[AuditItemOut]
    page: int
    page_size: int
    total: int


class AuditMessageOut(BaseModel):
    id: uuid.UUID
    target_chat_title: str
    telegram_message_id: int
    message_text: str
    message_link: str | None = None


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
