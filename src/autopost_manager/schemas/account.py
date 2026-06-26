from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field, field_validator

from autopost_manager.models import SessionStatus


class TelegramSessionOut(BaseModel):
    id: uuid.UUID
    name: str
    phone: str | None
    telegram_user_id: int | None
    username: str | None
    status: SessionStatus
    min_send_interval_seconds: int

    model_config = {"from_attributes": True}


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


class AccountPauseOut(BaseModel):
    autopost_paused: bool
    cancelled_jobs: int = 0


class AccountRevokeOut(BaseModel):
    revoked_sessions: int
    disabled_chats: int
    cancelled_jobs: int
    telegram_logout_errors: list[str] = Field(default_factory=list)
