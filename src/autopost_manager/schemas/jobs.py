from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from autopost_manager.models import JobStatus


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
