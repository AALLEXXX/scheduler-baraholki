from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from autopost_manager.models import TargetChat, TargetChatType


class TargetChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_enabled_for_owner(self, owner_telegram_id: int) -> list[TargetChat]:
        return list(
            self.db.scalars(
                select(TargetChat)
                .where(TargetChat.owner_telegram_id == owner_telegram_id)
                .where(TargetChat.enabled.is_(True))
                .order_by(TargetChat.title)
            )
        )

    def fetch_owned_enabled(self, chat_id: UUID, owner_telegram_id: int) -> TargetChat | None:
        return self.db.scalars(
            select(TargetChat)
            .where(TargetChat.id == chat_id)
            .where(TargetChat.owner_telegram_id == owner_telegram_id)
            .where(TargetChat.enabled.is_(True))
        ).first()

    def fetch_by_session_and_telegram_chat_id(
        self,
        *,
        session_id: UUID,
        telegram_chat_id: int,
    ) -> TargetChat | None:
        return self.db.scalars(
            select(TargetChat)
            .where(TargetChat.session_id == session_id)
            .where(TargetChat.telegram_chat_id == telegram_chat_id)
        ).first()

    def upsert_synced_dialog(
        self,
        *,
        owner_telegram_id: int,
        session_id: UUID,
        telegram_chat_id: int,
        title: str,
        username: str | None,
        chat_type: TargetChatType,
    ) -> bool:
        existing = self.fetch_by_session_and_telegram_chat_id(
            session_id=session_id,
            telegram_chat_id=telegram_chat_id,
        )
        if existing:
            existing.title = title
            existing.username = username
            existing.type = chat_type
            existing.enabled = True
            return False

        self.db.add(
            TargetChat(
                owner_telegram_id=owner_telegram_id,
                session_id=session_id,
                telegram_chat_id=telegram_chat_id,
                title=title,
                username=username,
                type=chat_type,
                enabled=True,
            )
        )
        return True
