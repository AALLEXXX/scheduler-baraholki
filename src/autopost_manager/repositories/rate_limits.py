from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from autopost_manager.models import RateLimitEvent


class RateLimitRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def delete_older_than(self, *, scope: str, cutoff: datetime) -> None:
        self.db.execute(
            delete(RateLimitEvent)
            .where(RateLimitEvent.scope == scope)
            .where(RateLimitEvent.created_at < cutoff)
        )

    def count_since(self, *, scope: str, key: str, since: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(RateLimitEvent)
                .where(RateLimitEvent.scope == scope)
                .where(RateLimitEvent.key == key)
                .where(RateLimitEvent.created_at >= since)
            )
            or 0
        )

    def add_event(self, *, scope: str, key: str, created_at: datetime) -> None:
        self.db.add(RateLimitEvent(scope=scope, key=key, created_at=created_at))
