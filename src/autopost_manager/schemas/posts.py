from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from autopost_manager.models import PostStatus, ScheduleKind
from autopost_manager.schemas.common import MAX_SCHEDULE_WEEKDAYS
from autopost_manager.schemas.common import MAX_TARGET_CHAT_IDS
from autopost_manager.schemas.common import ParseMode
from autopost_manager.schemas.common import SessionStrategy
from autopost_manager.schemas.common import ensure_timezone
from autopost_manager.schemas.common import normalize_schedule_weekdays


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4096)
    parse_mode: ParseMode | None = ParseMode.html
    status: PostStatus = PostStatus.draft
    schedule_kind: ScheduleKind = ScheduleKind.once
    next_run_at: datetime | None = None
    interval_minutes: int | None = Field(default=None, ge=1)
    schedule_weekdays: list[int] = Field(default_factory=list, max_length=MAX_SCHEDULE_WEEKDAYS)
    timezone: str = "Asia/Tbilisi"
    session_strategy: SessionStrategy = SessionStrategy.fixed
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
