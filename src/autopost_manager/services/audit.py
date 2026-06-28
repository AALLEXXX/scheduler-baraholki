from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from autopost_manager.models import SessionStatus, TargetChat, TelegramSession
from autopost_manager.repositories.audit import AuditRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.schemas import AuditItemOut, AuditMessageOut, AuditPageOut
from autopost_manager.telegram_client import TelegramMessageSnapshot

logger = logging.getLogger(__name__)

FetchMessage = Callable[..., Awaitable[TelegramMessageSnapshot | None]]
SendAlert = Callable[..., Awaitable[None]]


def telegram_message_link(chat: TargetChat, message_id: int | None) -> str | None:
    if not message_id:
        return None
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    chat_id = int(chat.telegram_chat_id)
    chat_id_text = str(abs(chat_id))
    if chat_id_text.startswith("100") and len(chat_id_text) > 3:
        return f"https://t.me/c/{chat_id_text[3:]}/{message_id}"
    return None


@dataclass(kw_only=True, frozen=True, slots=True)
class AuditService:
    db: Session
    fetch_message: FetchMessage
    send_alert: SendAlert

    def active_account(self, telegram_user_id: int) -> TelegramSession | None:
        return TelegramSessionRepository(self.db).active_for_owner(telegram_user_id)

    def audit_page_for_user(
        self,
        *,
        telegram_user_id: int,
        page: int,
        page_size: int,
    ) -> AuditPageOut:
        if not self.active_account(telegram_user_id):
            return AuditPageOut(items=[], page=page, page_size=page_size, total=0)

        audit_repository = AuditRepository(self.db)
        rows = audit_repository.list_for_owner(
            telegram_user_id=telegram_user_id,
            page=page,
            page_size=page_size,
        )
        return AuditPageOut(
            items=[
                AuditItemOut(
                    id=row.job.id,
                    post_id=row.post.id,
                    post_title=row.post.title,
                    post_preview=row.post.body,
                    media_count=len(row.post.media_items),
                    target_chat_id=row.chat.id,
                    target_chat_title=row.chat.title,
                    due_at=row.job.due_at,
                    updated_at=row.job.updated_at,
                    status=row.job.status,
                    attempts=row.job.attempts,
                    telegram_message_id=row.job.telegram_message_id,
                    message_link=telegram_message_link(row.chat, row.job.telegram_message_id),
                    last_error=row.job.last_error,
                )
                for row in rows
            ],
            page=page,
            page_size=page_size,
            total=audit_repository.count_for_owner(telegram_user_id),
        )

    async def audit_message_for_user(
        self,
        *,
        telegram_user_id: int,
        job_id: uuid.UUID,
    ) -> AuditMessageOut:
        row = AuditRepository(self.db).fetch_for_owner(telegram_user_id=telegram_user_id, job_id=job_id)
        if not row:
            raise HTTPException(status_code=404, detail="Audit item not found")

        job = row.job
        chat = row.chat
        if not job.telegram_message_id:
            raise HTTPException(status_code=404, detail="Telegram message id is not available")

        session = job.session
        if not session or session.owner_telegram_id != telegram_user_id or session.status != SessionStatus.active:
            session = self.active_account(telegram_user_id)
        if not session:
            raise HTTPException(status_code=409, detail="Connect Telegram account to view this message")

        try:
            message = await self.fetch_message(
                session=session,
                peer=chat.telegram_chat_id,
                message_id=job.telegram_message_id,
            )
        except RuntimeError as exc:
            logger.warning("Telegram audit message lookup failed: job_id=%s error=%s", job.id, exc)
            await self.send_alert(
                title="Audit message lookup error",
                status="409",
                fields={
                    "action": "view_audit_message",
                    "owner_telegram_id": telegram_user_id,
                    "job_id": job.id,
                    "target_telegram_chat_id": chat.telegram_chat_id,
                    "target_title": chat.title,
                    "telegram_message_id": job.telegram_message_id,
                    "error_type": type(exc).__name__,
                    "error": exc,
                },
            )
            raise HTTPException(status_code=409, detail="Не удалось получить сообщение из Telegram") from exc

        if not message:
            raise HTTPException(status_code=404, detail="Message not found in Telegram chat")

        return AuditMessageOut(
            id=job.id,
            target_chat_title=chat.title,
            telegram_message_id=job.telegram_message_id,
            message_text=message.text,
            message_link=telegram_message_link(chat, job.telegram_message_id),
        )
