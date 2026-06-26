from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from autopost_manager.models import SessionStatus, TelegramSession
from autopost_manager.repositories.posts import PostRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.repositories.target_chats import TargetChatRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.user_settings import UserSettingsRepository
from autopost_manager.schemas import AccountPauseOut, AccountRevokeOut, UserSettingsOut

LogoutSession = Callable[[TelegramSession], Awaitable[None]]
DeleteSessionFiles = Callable[[str | None], None]


@dataclass(slots=True)
class AccountService:
    db: Session

    def user_settings(self, *, telegram_user_id: int) -> UserSettingsOut:
        settings = UserSettingsRepository(self.db).get_or_create(telegram_user_id)
        self.db.commit()
        return UserSettingsOut(autopost_paused=settings.autopost_paused)

    def list_sessions(self, *, telegram_user_id: int) -> list[TelegramSession]:
        return TelegramSessionRepository(self.db).list_for_owner(telegram_user_id)

    def pause_autoposting(self, *, telegram_user_id: int) -> AccountPauseOut:
        settings = UserSettingsRepository(self.db).get_or_create(telegram_user_id)
        settings.autopost_paused = True
        cancelled = PublishJobRepository(self.db).cancel_pending_for_owner(telegram_user_id)
        self.db.commit()
        return AccountPauseOut(autopost_paused=True, cancelled_jobs=cancelled)

    def resume_autoposting(self, *, telegram_user_id: int) -> AccountPauseOut:
        settings = UserSettingsRepository(self.db).get_or_create(telegram_user_id)
        settings.autopost_paused = False
        self.db.commit()
        return AccountPauseOut(autopost_paused=False, cancelled_jobs=0)

    async def revoke_account(
        self,
        *,
        telegram_user_id: int,
        logout_session: LogoutSession,
        delete_session_files: DeleteSessionFiles,
    ) -> AccountRevokeOut:
        sessions = TelegramSessionRepository(self.db).list_non_revoked_for_owner(telegram_user_id)
        chats = TargetChatRepository(self.db).list_enabled_for_owner(telegram_user_id)

        telegram_logout_errors: list[str] = []
        for session in sessions:
            try:
                await logout_session(session)
            except Exception as exc:
                telegram_logout_errors.append(f"{session.id}: {exc}")
            session.status = SessionStatus.revoked
            session.phone_code_hash = None
            session.session_string = None
            delete_session_files(session.session_path)

        for chat in chats:
            chat.enabled = False

        PostRepository(self.db).pause_scheduled_for_owner(telegram_user_id)
        cancelled = PublishJobRepository(self.db).cancel_pending_for_owner(telegram_user_id)
        settings = UserSettingsRepository(self.db).get_or_create(telegram_user_id)
        settings.autopost_paused = True

        self.db.commit()
        return AccountRevokeOut(
            revoked_sessions=len(sessions),
            disabled_chats=len(chats),
            cancelled_jobs=cancelled,
            telegram_logout_errors=telegram_logout_errors,
        )
