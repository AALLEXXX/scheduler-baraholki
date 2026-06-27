from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autopost_manager.models import SessionStatus, TelegramSession


class TelegramSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_by_id(self, session_id: UUID) -> TelegramSession | None:
        return self.db.get(TelegramSession, session_id)

    def fetch_owned(self, session_id: UUID, owner_telegram_id: int) -> TelegramSession | None:
        session = self.fetch_by_id(session_id)
        if not session or session.owner_telegram_id != owner_telegram_id:
            return None
        return session

    def fetch_owned_active(self, session_id: UUID, owner_telegram_id: int) -> TelegramSession | None:
        session = self.fetch_owned(session_id, owner_telegram_id)
        if not session or session.status != SessionStatus.active:
            return None
        return session

    def name_exists_for_owner(self, *, owner_telegram_id: int, name: str) -> bool:
        return bool(
            self.db.scalar(
                select(TelegramSession.id)
                .where(TelegramSession.owner_telegram_id == owner_telegram_id)
                .where(TelegramSession.name == name)
            )
        )

    def list_for_owner(self, owner_telegram_id: int) -> list[TelegramSession]:
        return list(
            self.db.scalars(
                select(TelegramSession)
                .where(TelegramSession.owner_telegram_id == owner_telegram_id)
                .order_by(TelegramSession.created_at.desc())
            )
        )

    def list_active_for_owner(self, owner_telegram_id: int) -> list[TelegramSession]:
        return list(
            self.db.scalars(
                select(TelegramSession)
                .where(TelegramSession.owner_telegram_id == owner_telegram_id)
                .where(TelegramSession.status == SessionStatus.active)
                .order_by(TelegramSession.updated_at.desc())
            )
        )

    def list_non_revoked_for_owner(self, owner_telegram_id: int) -> list[TelegramSession]:
        return list(
            self.db.scalars(
                select(TelegramSession)
                .where(TelegramSession.owner_telegram_id == owner_telegram_id)
                .where(TelegramSession.status != SessionStatus.revoked)
            )
        )

    def latest_for_owner(self, owner_telegram_id: int) -> TelegramSession | None:
        return self.db.scalars(
            select(TelegramSession)
            .where(TelegramSession.owner_telegram_id == owner_telegram_id)
            .order_by(TelegramSession.updated_at.desc())
        ).first()

    def active_for_owner(self, owner_telegram_id: int) -> TelegramSession | None:
        return self.db.scalars(
            select(TelegramSession)
            .where(TelegramSession.owner_telegram_id == owner_telegram_id)
            .where(TelegramSession.status == SessionStatus.active)
            .order_by(TelegramSession.updated_at.desc())
        ).first()

    def least_recently_used_active_for_owner(self, owner_telegram_id: int) -> TelegramSession | None:
        return self.db.scalars(
            select(TelegramSession)
            .where(TelegramSession.owner_telegram_id == owner_telegram_id)
            .where(TelegramSession.status == SessionStatus.active)
            .order_by(TelegramSession.last_send_at.asc().nullsfirst())
            .limit(1)
        ).first()

    def count_for_owner(self, owner_telegram_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(TelegramSession)
                .where(TelegramSession.owner_telegram_id == owner_telegram_id)
            )
            or 0
        )

    def count_non_revoked_for_owner(self, owner_telegram_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(TelegramSession)
                .where(TelegramSession.owner_telegram_id == owner_telegram_id)
                .where(TelegramSession.status != SessionStatus.revoked)
            )
            or 0
        )
