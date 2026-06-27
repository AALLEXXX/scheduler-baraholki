from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    PhonePasswordFloodError,
    SendCodeUnavailableError,
)

from autopost_manager.config import Settings
from autopost_manager.models import SessionStatus, TelegramSession
from autopost_manager.repositories.posts import PostRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.repositories.rate_limits import RateLimitRepository
from autopost_manager.repositories.target_chats import TargetChatRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.user_settings import UserSettingsRepository
from autopost_manager.schemas import (
    AccountCodeConfirm,
    AccountLoginOut,
    AccountPasswordConfirm,
    AccountPauseOut,
    AccountRevokeOut,
    AccountStartLogin,
    UserSettingsOut,
)
from autopost_manager.services.admin import mask_phone

LogoutSession = Callable[[TelegramSession], Awaitable[None]]
DeleteSessionFiles = Callable[[str | None], None]
SendAlert = Callable[..., Awaitable[None]]
RequestLoginCode = Callable[..., Awaitable[object]]
ConfirmLoginCode = Callable[[TelegramSession, str], Awaitable[tuple[bool, object]]]
ConfirmLoginPassword = Callable[[TelegramSession, str], Awaitable[object]]

LOGIN_CODE_COOLDOWN_SECONDS = 90
RATE_LIMIT_LOGIN_START_WINDOW_SECONDS = 10 * 60
RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_LOGIN_START_ATTEMPTS = 3
RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS = 5

logger = logging.getLogger(__name__)


def login_error_detail(stage: str, exc: Exception) -> str:
    if isinstance(exc, FloodWaitError):
        return f"Telegram временно ограничил попытки. Попробуйте через {exc.seconds} сек."
    if isinstance(exc, PhoneNumberFloodError):
        return "Telegram временно ограничил отправку кодов на этот номер. Попробуйте позже."
    if isinstance(exc, PhonePasswordFloodError):
        return "Telegram временно ограничил попытки ввода 2FA-пароля. Попробуйте позже."
    if isinstance(exc, PhoneNumberInvalidError):
        return "Telegram не принял номер. Проверьте формат: номер должен быть с кодом страны, например +995..."
    if isinstance(exc, PhoneNumberBannedError):
        return "Telegram не разрешает вход для этого номера: аккаунт заблокирован или ограничен."
    if isinstance(exc, (PhoneCodeEmptyError, PhoneCodeInvalidError)):
        return "Telegram не принял код. Проверьте код и попробуйте ещё раз."
    if isinstance(exc, PhoneCodeExpiredError):
        return "Код Telegram истёк. Нажмите «Получить код» ещё раз."
    if isinstance(exc, SendCodeUnavailableError):
        return "Telegram не даёт отправить SMS для этого номера сейчас. Проверьте код в Telegram-приложении или попробуйте позже."
    if isinstance(exc, PasswordHashInvalidError):
        return "Telegram не принял пароль 2FA. Нужен облачный пароль из настроек Telegram, не код из сообщения."
    prefix = {
        "start-login": "Не удалось отправить код Telegram",
        "confirm-code": "Не удалось подтвердить код Telegram",
        "confirm-password": "Не удалось подтвердить пароль 2FA",
    }.get(stage, "Telegram вернул ошибку")
    return f"{prefix}. Попробуйте позже или проверьте данные."


def login_code_message(delivery_type: str | None, *, force_sms: bool) -> str:
    if delivery_type == "SentCodeTypeSms":
        return "Telegram отправил код по SMS."
    if delivery_type == "SentCodeTypeCall":
        return "Telegram отправит код звонком."
    if delivery_type == "SentCodeTypeFlashCall":
        return "Telegram отправит код через flash-call."
    if delivery_type == "SentCodeTypeApp":
        return "Telegram отправил код в Telegram-приложение или служебный чат на активном устройстве, не по SMS."
    if force_sms:
        return "Запросили SMS-код. Если Telegram разрешил SMS, код придёт на номер."
    return "Telegram принял запрос на код. Если SMS не пришла, проверьте Telegram-приложение на других устройствах."


def remaining_login_code_cooldown(session: TelegramSession) -> int:
    if not session.last_code_requested_at:
        return 0
    last_requested = session.last_code_requested_at
    if last_requested.tzinfo is None:
        last_requested = last_requested.replace(tzinfo=UTC)
    elapsed = datetime.now(UTC) - last_requested
    remaining = timedelta(seconds=LOGIN_CODE_COOLDOWN_SECONDS) - elapsed
    return max(0, int(remaining.total_seconds()))


def phone_digits(phone: str | None) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def normalize_phone_key(phone: str) -> str:
    digits = phone_digits(phone)
    return digits[-12:] if digits else "unknown"


@dataclass(slots=True)
class AccountService:
    db: Session

    async def raise_login_error(
        self,
        *,
        stage: str,
        session: TelegramSession,
        exc: Exception,
        send_alert: SendAlert,
    ) -> None:
        logger.warning(
            "Telegram login failed: stage=%s session_id=%s owner=%s error_type=%s error=%s",
            stage,
            session.id,
            session.owner_telegram_id,
            type(exc).__name__,
            exc,
        )
        await send_alert(
            title="Telegram login error",
            status="422",
            fields={
                "action": stage,
                "owner_telegram_id": session.owner_telegram_id,
                "session_id": session.id,
                "session_status": session.status.value,
                "phone": mask_phone(session.phone),
                "error_type": type(exc).__name__,
                "error": login_error_detail(stage, exc),
            },
        )
        raise HTTPException(status_code=422, detail=login_error_detail(stage, exc)) from exc

    def check_rate_limit(
        self,
        *,
        scope: str,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=window_seconds)
        rate_limits = RateLimitRepository(self.db)
        rate_limits.delete_older_than(scope=scope, cutoff=cutoff)
        count = rate_limits.count_since(scope=scope, key=key, since=cutoff)
        if count >= limit:
            raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")
        rate_limits.add_event(scope=scope, key=key, created_at=now)

    def find_session_by_phone(self, *, owner_telegram_id: int, phone: str) -> TelegramSession | None:
        target_digits = phone_digits(phone)
        if not target_digits:
            return None
        sessions = TelegramSessionRepository(self.db).list_for_owner(owner_telegram_id)
        return next((session for session in sessions if phone_digits(session.phone) == target_digits), None)

    def unique_session_name(self, *, owner_telegram_id: int, safe_phone: str) -> str:
        sessions = TelegramSessionRepository(self.db)
        base_name = f"tg_{owner_telegram_id}_{safe_phone or 'account'}"
        if not sessions.name_exists_for_owner(owner_telegram_id=owner_telegram_id, name=base_name):
            return base_name

        for index in range(2, 100):
            candidate = f"{base_name}_{index}"
            if not sessions.name_exists_for_owner(owner_telegram_id=owner_telegram_id, name=candidate):
                return candidate
        return f"{base_name}_{uuid.uuid4().hex[:8]}"

    async def start_login(
        self,
        *,
        payload: AccountStartLogin,
        telegram_user_id: int,
        settings: Settings,
        request_login_code: RequestLoginCode,
        send_alert: SendAlert,
    ) -> AccountLoginOut:
        self.check_rate_limit(
            scope="login:start",
            key=f"{telegram_user_id}:{normalize_phone_key(payload.phone)}",
            limit=RATE_LIMIT_LOGIN_START_ATTEMPTS,
            window_seconds=RATE_LIMIT_LOGIN_START_WINDOW_SECONDS,
        )
        safe_phone = phone_digits(payload.phone)
        session = self.find_session_by_phone(owner_telegram_id=telegram_user_id, phone=payload.phone)
        if not session:
            if TelegramSessionRepository(self.db).count_non_revoked_for_owner(telegram_user_id) >= settings.max_sessions_per_user:
                raise HTTPException(status_code=429, detail="Достигнут лимит Telegram-аккаунтов")
            session_name = self.unique_session_name(owner_telegram_id=telegram_user_id, safe_phone=safe_phone)
            session_path = str(settings.telegram_sessions_dir / session_name)
            session = TelegramSession(
                owner_telegram_id=telegram_user_id,
                name=session_name,
                phone=payload.phone,
                api_id=settings.telegram_api_id,
                api_hash=settings.telegram_api_hash,
                session_path=session_path,
                status=SessionStatus.credentials_needed,
                min_send_interval_seconds=settings.default_min_send_interval_seconds,
            )
            self.db.add(session)
            self.db.flush()
        else:
            session.phone = payload.phone
            session.api_id = settings.telegram_api_id
            session.api_hash = settings.telegram_api_hash
            session_name = session.name or self.unique_session_name(owner_telegram_id=telegram_user_id, safe_phone=safe_phone)
            session_path = str(settings.telegram_sessions_dir / session_name)
            session.name = session.name or session_name
            session.session_path = session.session_path or session_path

        cooldown_seconds = remaining_login_code_cooldown(session)
        if cooldown_seconds:
            raise HTTPException(
                status_code=429,
                detail=f"Повторно запросить код можно через {cooldown_seconds} сек.",
            )
        self.db.commit()

        try:
            code_request = await request_login_code(session, force_sms=payload.force_sms)
        except Exception as exc:
            session.phone_code_hash = None
            self.db.commit()
            await self.raise_login_error(stage="start-login", session=session, exc=exc, send_alert=send_alert)

        session.phone_code_hash = code_request.phone_code_hash
        session.status = SessionStatus.code_needed
        session.last_code_requested_at = datetime.now(UTC)
        logger.warning(
            "Telegram login code requested: session_id=%s owner=%s delivery_type=%s next_delivery_type=%s force_sms=%s timeout=%s",
            session.id,
            session.owner_telegram_id,
            code_request.delivery_type,
            code_request.next_delivery_type,
            payload.force_sms,
            code_request.timeout,
        )
        self.db.commit()
        return AccountLoginOut(
            session_id=session.id,
            status=session.status,
            message=login_code_message(code_request.delivery_type, force_sms=payload.force_sms),
            delivery_type=code_request.delivery_type,
            next_delivery_type=code_request.next_delivery_type,
        )

    async def confirm_code(
        self,
        *,
        payload: AccountCodeConfirm,
        telegram_user_id: int,
        confirm_login_code: ConfirmLoginCode,
        send_alert: SendAlert,
    ) -> AccountLoginOut:
        session = TelegramSessionRepository(self.db).fetch_owned(payload.session_id, telegram_user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Telegram account not found")
        self.check_rate_limit(
            scope="login:code",
            key=str(session.id),
            limit=RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS,
            window_seconds=RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS,
        )

        try:
            completed, me = await confirm_login_code(session, payload.code)
        except Exception as exc:
            session.phone_code_hash = None
            self.db.commit()
            await self.raise_login_error(stage="confirm-code", session=session, exc=exc, send_alert=send_alert)

        if not completed:
            session.status = SessionStatus.password_needed
            self.db.commit()
            return AccountLoginOut(
                session_id=session.id,
                status=session.status,
                message="Two-step verification is enabled. Enter your Telegram password.",
            )

        session.telegram_user_id = me.id
        session.username = me.username
        session.status = SessionStatus.active
        session.phone_code_hash = None
        UserSettingsRepository(self.db).get_or_create(telegram_user_id).autopost_paused = False
        self.db.commit()
        return AccountLoginOut(session_id=session.id, status=session.status, message="Account connected.")

    async def confirm_password(
        self,
        *,
        payload: AccountPasswordConfirm,
        telegram_user_id: int,
        confirm_login_password: ConfirmLoginPassword,
        send_alert: SendAlert,
    ) -> AccountLoginOut:
        session = TelegramSessionRepository(self.db).fetch_owned(payload.session_id, telegram_user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Telegram account not found")
        self.check_rate_limit(
            scope="login:password",
            key=str(session.id),
            limit=RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS,
            window_seconds=RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS,
        )

        try:
            me = await confirm_login_password(session, payload.password)
        except Exception as exc:
            session.phone_code_hash = None
            self.db.commit()
            await self.raise_login_error(stage="confirm-password", session=session, exc=exc, send_alert=send_alert)

        session.telegram_user_id = me.id
        session.username = me.username
        session.status = SessionStatus.active
        session.phone_code_hash = None
        UserSettingsRepository(self.db).get_or_create(telegram_user_id).autopost_paused = False
        self.db.commit()
        return AccountLoginOut(session_id=session.id, status=session.status, message="Account connected.")

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
