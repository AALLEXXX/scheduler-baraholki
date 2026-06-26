from __future__ import annotations

from sqlalchemy.orm import Session

from autopost_manager.models import UserSettings


class UserSettingsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_by_user_id(self, telegram_user_id: int) -> UserSettings | None:
        return self.db.get(UserSettings, telegram_user_id)

    def get_or_create(self, telegram_user_id: int) -> UserSettings:
        settings = self.fetch_by_user_id(telegram_user_id)
        if settings:
            return settings
        settings = UserSettings(telegram_user_id=telegram_user_id)
        self.db.add(settings)
        self.db.flush()
        return settings
