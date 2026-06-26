from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from autopost_manager.models import JobStatus


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
