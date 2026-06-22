from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

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


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4096)
    parse_mode: str | None = "html"
    status: PostStatus = PostStatus.draft
    schedule_kind: ScheduleKind = ScheduleKind.once
    next_run_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    timezone: str = "Asia/Tbilisi"
    session_strategy: str = "fixed"
    default_session_id: uuid.UUID | None = None
    target_chat_ids: list[uuid.UUID] = []


class PostOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    parse_mode: str | None
    status: PostStatus
    schedule_kind: ScheduleKind
    next_run_at: datetime | None
    interval_minutes: int | None
    timezone: str
    session_strategy: str
    default_session_id: uuid.UUID | None
    target_chat_ids: list[uuid.UUID]


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
