from __future__ import annotations

import uuid
from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator

from autopost_manager.models import JobStatus, PostStatus, ScheduleKind, SessionStatus, TargetChatType


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
    parse_mode: str | None = "html"
    status: PostStatus = PostStatus.draft
    schedule_kind: ScheduleKind = ScheduleKind.once
    next_run_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    schedule_weekdays: list[int] = Field(default_factory=list)
    timezone: str = "Asia/Tbilisi"
    session_strategy: str = "fixed"
    default_session_id: uuid.UUID | None = None
    target_chat_ids: list[uuid.UUID] = Field(default_factory=list)
    spam_risk_acknowledged: bool = False


class PostScheduleUpdate(BaseModel):
    schedule_kind: ScheduleKind = ScheduleKind.once
    next_run_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    schedule_weekdays: list[int] = Field(default_factory=list)
    timezone: str = "Asia/Tbilisi"
    default_session_id: uuid.UUID
    target_chat_ids: list[uuid.UUID] = Field(default_factory=list)
    spam_risk_acknowledged: bool = False


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
    parse_mode: str | None
    status: PostStatus
    schedule_kind: ScheduleKind
    next_run_at: datetime | None
    interval_minutes: int | None
    schedule_weekdays: list[int] = Field(default_factory=list)
    timezone: str
    session_strategy: str
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
    last_error: str | None


class AuditPageOut(BaseModel):
    items: list[AuditItemOut]
    page: int
    page_size: int
    total: int
