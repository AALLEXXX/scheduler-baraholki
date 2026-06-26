from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from autopost_manager.models import TargetChatType


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


class ChatSyncResult(BaseModel):
    imported: int
    total_dialogs: int
