from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import logging
import uuid
from pathlib import Path

import uvicorn
from aiogram import Bot
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import delete, func, select
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

from autopost_manager.alerts import send_alert
from autopost_manager.config import get_settings
from autopost_manager.db import get_db
from autopost_manager.messages import POST_SAVED_ACK_TEXT
from autopost_manager.models import (
    Post,
    PostStatus,
    PublishJob,
    RateLimitEvent,
    ScheduleKind,
    SessionStatus,
    TargetChat,
    TelegramSession,
    UserSettings,
)
from autopost_manager.schemas import (
    AccountCodeConfirm,
    AccountLoginOut,
    AccountPauseOut,
    AccountPasswordConfirm,
    AccountRevokeOut,
    AccountStartLogin,
    AdminStatsOut,
    AdminUserOut,
    AdminUserPageOut,
    AdminUserUpdate,
    AppConfigOut,
    AuditMessageOut,
    AuditPageOut,
    DeletePostOut,
    DialogFolderOut,
    PostCreate,
    PostMediaOut,
    PostOut,
    PostResumeUpdate,
    PostScheduleUpdate,
    TargetChatCreate,
    UserSettingsOut,
)
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.posts import PostRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.schedule import WeekdaySet
from autopost_manager.security import require_user, verify_webapp_init_data
from autopost_manager.services.admin import AdminService
from autopost_manager.services.admin import day_start as admin_day_start
from autopost_manager.services.admin import failed_total as admin_failed_total
from autopost_manager.services.admin import mask_phone as admin_mask_phone
from autopost_manager.services.admin import sent_since as admin_sent_since
from autopost_manager.services.audit import AuditService
from autopost_manager.services.audit import telegram_message_link as audit_telegram_message_link
from autopost_manager.services.account import AccountService
from autopost_manager.services.chats import ChatService
from autopost_manager.telegram_client import (
    confirm_login_code,
    confirm_login_password,
    delete_messages_from_session,
    get_message_from_session,
    list_dialog_folders_from_session,
    list_dialogs_from_session,
    logout_session_from_telegram,
    request_login_code,
)

logger = logging.getLogger(__name__)
LOGIN_CODE_COOLDOWN_SECONDS = 90
RATE_LIMIT_LOGIN_START_WINDOW_SECONDS = 10 * 60
RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_LOGIN_START_ATTEMPTS = 3
RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS = 5


def request_user_id(request: Request) -> int | None:
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        return None
    try:
        return verify_webapp_init_data(
            init_data,
            get_settings().bot_token,
            max_age_seconds=get_settings().telegram_init_data_max_age_seconds,
        )
    except ValueError:
        return None


async def alert_unhandled_errors(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        await send_alert(
            title="Unhandled API exception",
            status="500",
            fields={
                "action": "api_request",
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "telegram_user_id": request_user_id(request),
                "error_type": type(exc).__name__,
                "error": exc,
            },
        )
        raise


async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self' https://telegram.org https://*.telegram.org; "
        "script-src 'self' 'unsafe-inline' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://*.telegram.org https://api.telegram.org; "
        "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org;",
    )
    return response


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


async def raise_login_error(stage: str, session: TelegramSession, exc: Exception) -> None:
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


def validate_runtime_settings() -> None:
    settings = get_settings()
    if settings.app_env != "local" and settings.allow_local_auth_bypass:
        raise RuntimeError("ALLOW_LOCAL_AUTH_BYPASS must be disabled outside local")
    if settings.app_env != "local" and not settings.app_encryption_key:
        raise RuntimeError("APP_ENCRYPTION_KEY is required outside local")
    if settings.allow_local_auth_bypass and not settings.local_dev_user_id:
        raise RuntimeError("LOCAL_DEV_USER_ID is required when local auth bypass is enabled")


def startup() -> None:
    validate_runtime_settings()
    get_settings().telegram_sessions_dir.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
    startup()
    yield


@dataclass
class BotMessageDeleteResult:
    attempted: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


def post_to_out(post: Post) -> PostOut:
    return PostOut(
        id=post.id,
        title=post.title,
        body=post.body,
        parse_mode=post.parse_mode,
        status=post.status,
        schedule_kind=post.schedule_kind,
        next_run_at=post.next_run_at,
        interval_minutes=post.interval_minutes,
        schedule_weekdays=parse_schedule_weekdays(post.schedule_weekdays),
        timezone=post.timezone,
        session_strategy=post.session_strategy,
        default_session_id=post.default_session_id,
        target_chat_ids=[target.target_chat_id for target in post.targets],
        media=[
            PostMediaOut.model_validate(media)
            for media in sorted(post.media_items, key=lambda item: item.order_index)
        ],
    )


def collect_source_message_refs(post: Post) -> set[tuple[int, int]]:
    refs: set[tuple[int, int]] = set()
    if post.source_bot_chat_id and post.source_bot_message_id:
        refs.add((post.source_bot_chat_id, post.source_bot_message_id))
    if post.ack_bot_chat_id and post.ack_bot_message_id:
        refs.add((post.ack_bot_chat_id, post.ack_bot_message_id))
    for media in post.media_items:
        refs.add((media.source_bot_chat_id, media.source_bot_message_id))
    return refs


def as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_schedule_weekdays(value: str | None) -> list[int]:
    return WeekdaySet.parse_storage_value(value).as_list()


def serialize_schedule_weekdays(values: list[int] | None) -> str | None:
    return WeekdaySet.from_request(values).serialize_for_storage()


def schedule_weekdays_for_storage(
    schedule_kind: ScheduleKind,
    values: list[int] | None,
) -> str | None:
    if schedule_kind != ScheduleKind.custom_weekdays:
        return None
    return serialize_schedule_weekdays(values)


def cancel_pending_jobs(post: Post, db: Session) -> int:
    return PublishJobRepository(db).cancel_pending_for_post(post.id)


def active_account(
    *,
    telegram_user_id: int,
    db: Session,
) -> TelegramSession | None:
    return db.scalars(
        select(TelegramSession)
        .where(TelegramSession.owner_telegram_id == telegram_user_id)
        .where(TelegramSession.status == SessionStatus.active)
        .order_by(TelegramSession.updated_at.desc())
    ).first()


def telegram_message_link(chat: TargetChat, message_id: int | None) -> str | None:
    return audit_telegram_message_link(chat, message_id)


def user_settings(
    *,
    telegram_user_id: int,
    db: Session,
) -> UserSettings:
    settings = db.get(UserSettings, telegram_user_id)
    if settings:
        return settings
    settings = UserSettings(telegram_user_id=telegram_user_id)
    db.add(settings)
    db.flush()
    return settings


def autopost_paused(
    *,
    telegram_user_id: int,
    db: Session,
) -> bool:
    settings = db.get(UserSettings, telegram_user_id)
    return bool(settings and settings.autopost_paused)


def is_admin_id(telegram_user_id: int | None) -> bool:
    if telegram_user_id is None:
        return False
    settings = get_settings()
    if (
        settings.app_env == "local"
        and settings.allow_local_auth_bypass
        and not settings.admin_ids
        and telegram_user_id == settings.local_dev_user_id
    ):
        return True
    return telegram_user_id in settings.admin_ids


def optional_telegram_user_id(
    x_telegram_init_data: str | None = Header(default=None),
) -> int | None:
    settings = get_settings()
    if settings.app_env == "local" and settings.allow_local_auth_bypass and not x_telegram_init_data:
        return settings.local_dev_user_id
    if not x_telegram_init_data:
        return None
    try:
        return verify_webapp_init_data(
            x_telegram_init_data,
            settings.bot_token,
            max_age_seconds=settings.telegram_init_data_max_age_seconds,
        )
    except ValueError:
        return None


def require_admin_user(telegram_user_id: int = Depends(require_user)) -> int:
    if not is_admin_id(telegram_user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return telegram_user_id


def day_start() -> datetime:
    return admin_day_start()


def tomorrow_start() -> datetime:
    return day_start() + timedelta(days=1)


def check_rate_limit(
    db: Session,
    *,
    scope: str,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=window_seconds)
    db.execute(
        delete(RateLimitEvent)
        .where(RateLimitEvent.scope == scope)
        .where(RateLimitEvent.created_at < cutoff)
    )
    count = int(
        db.scalar(
            select(func.count())
            .select_from(RateLimitEvent)
            .where(RateLimitEvent.scope == scope)
            .where(RateLimitEvent.key == key)
            .where(RateLimitEvent.created_at >= cutoff)
        )
        or 0
    )
    if count >= limit:
        raise HTTPException(status_code=429, detail="Слишком много попыток. Попробуйте позже.")
    db.add(RateLimitEvent(scope=scope, key=key, created_at=now))


def normalize_phone_key(phone: str) -> str:
    digits = phone_digits(phone)
    return digits[-12:] if digits else "unknown"


def phone_digits(phone: str | None) -> str:
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def find_session_by_phone(db: Session, *, owner_telegram_id: int, phone: str) -> TelegramSession | None:
    target_digits = phone_digits(phone)
    if not target_digits:
        return None
    sessions = db.scalars(
        select(TelegramSession)
        .where(TelegramSession.owner_telegram_id == owner_telegram_id)
        .order_by(TelegramSession.created_at.desc())
    ).all()
    return next((session for session in sessions if phone_digits(session.phone) == target_digits), None)


def unique_session_name(db: Session, *, owner_telegram_id: int, safe_phone: str) -> str:
    base_name = f"tg_{owner_telegram_id}_{safe_phone or 'account'}"
    existing = db.scalar(select(TelegramSession.id).where(TelegramSession.name == base_name))
    if not existing:
        return base_name

    for index in range(2, 100):
        candidate = f"{base_name}_{index}"
        existing = db.scalar(select(TelegramSession.id).where(TelegramSession.name == candidate))
        if not existing:
            return candidate
    return f"{base_name}_{uuid.uuid4().hex[:8]}"


def sent_since(db: Session, *, telegram_user_id: int | None = None, since: datetime | None = None) -> int:
    return admin_sent_since(db, telegram_user_id=telegram_user_id, since=since)


def failed_total(db: Session, *, telegram_user_id: int | None = None) -> int:
    return admin_failed_total(db, telegram_user_id=telegram_user_id)


def require_autopost_enabled(
    *,
    telegram_user_id: int,
    db: Session,
) -> None:
    settings = db.get(UserSettings, telegram_user_id)
    if settings and settings.banned:
        raise HTTPException(status_code=403, detail="Пользователь заблокирован администратором")
    if settings and settings.autopost_paused:
        raise HTTPException(status_code=409, detail="Автопостинг на паузе")
    if settings and settings.daily_send_limit is not None:
        if sent_since(db, telegram_user_id=telegram_user_id, since=day_start()) >= settings.daily_send_limit:
            raise HTTPException(status_code=429, detail="Достигнут дневной лимит отправки постов")


def active_scheduled_posts_count(db: Session, telegram_user_id: int) -> int:
    return PostRepository(db).count_active_scheduled_for_owner(telegram_user_id)


def user_sessions_count(db: Session, telegram_user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(TelegramSession)
            .where(TelegramSession.owner_telegram_id == telegram_user_id)
            .where(TelegramSession.status != SessionStatus.revoked)
        )
        or 0
    )


def enforce_active_post_limit(
    db: Session,
    telegram_user_id: int,
    *,
    current_post: Post | None = None,
) -> None:
    settings = get_settings()
    count = active_scheduled_posts_count(db, telegram_user_id)
    if current_post and current_post.status == PostStatus.scheduled:
        count -= 1
    if count >= settings.max_active_posts_per_user:
        raise HTTPException(status_code=429, detail="Достигнут лимит активных запланированных постов")


def enforce_daily_job_creation_limit(db: Session, telegram_user_id: int, jobs_to_create: int) -> None:
    settings = get_settings()
    today_jobs = PublishJobRepository(db).count_created_since_for_owner(
        owner_telegram_id=telegram_user_id,
        since=day_start(),
    )
    if today_jobs + jobs_to_create > settings.max_jobs_per_user_per_day:
        raise HTTPException(status_code=429, detail="Достигнут дневной лимит постановки задач в очередь")


def mask_phone(phone: str | None) -> str | None:
    return admin_mask_phone(phone)


def require_active_account(
    *,
    telegram_user_id: int,
    db: Session,
) -> TelegramSession:
    session = active_account(telegram_user_id=telegram_user_id, db=db)
    if not session:
        raise HTTPException(status_code=409, detail="Сначала подключите Telegram-аккаунт")
    return session


async def delete_bot_messages(refs: set[tuple[int, int]]) -> BotMessageDeleteResult:
    result = BotMessageDeleteResult()
    if not refs:
        return result

    bot = Bot(token=get_settings().bot_token)
    try:
        for chat_id, message_id in refs:
            result.attempted += 1
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as exc:
                result.errors.append(f"{chat_id}/{message_id}: {exc}")
                await send_alert(
                    title="Bot message delete error",
                    status="error",
                    fields={
                        "action": "delete_bot_message",
                        "bot_chat_id": chat_id,
                        "bot_message_id": message_id,
                        "error_type": type(exc).__name__,
                        "error": exc,
                    },
                )
                continue
            result.deleted += 1
    finally:
        await bot.session.close()
    return result


async def delete_source_messages(
    *,
    telegram_user_id: int,
    refs: set[tuple[int, int]],
    db: Session,
    match_texts: set[str] | None = None,
    ack_text: str | None = None,
    created_at=None,
    media_count: int = 0,
) -> BotMessageDeleteResult:
    if not refs and not match_texts and not ack_text and not media_count:
        return BotMessageDeleteResult()

    message_ids = sorted({message_id for _chat_id, message_id in refs})
    session = db.scalars(
        select(TelegramSession)
        .where(TelegramSession.owner_telegram_id == telegram_user_id)
        .where(TelegramSession.status == SessionStatus.active)
        .order_by(TelegramSession.updated_at.desc())
    ).first()
    if not session:
        return await delete_bot_messages(refs)

    result = BotMessageDeleteResult(attempted=len(message_ids))
    try:
        bot_peer = f"@{get_settings().bot_username.lstrip('@')}"
        result.deleted = await delete_messages_from_session(
            session=session,
            peer=bot_peer,
            message_ids=message_ids,
            match_texts=match_texts,
            ack_text=ack_text,
            created_at=created_at,
            media_count=media_count,
        )
        result.attempted = max(result.attempted, result.deleted)
    except Exception as exc:
        result.errors.append(f"user session: {exc}")
        await send_alert(
            title="Source message delete error",
            status="error",
            fields={
                "action": "delete_source_messages",
                "owner_telegram_id": telegram_user_id,
                "source_message_ids": ",".join(str(message_id) for message_id in message_ids),
                "error_type": type(exc).__name__,
                "error": exc,
            },
        )

    if result.deleted == 0:
        fallback = await delete_bot_messages(refs)
        result.attempted += fallback.attempted
        result.deleted += fallback.deleted
        result.errors.extend(fallback.errors)

    return result


def validate_post_schedule(
    *,
    schedule_kind: ScheduleKind,
    next_run_at: datetime | None,
    interval_minutes: int | None,
    schedule_weekdays: list[int] | None,
    spam_risk_acknowledged: bool,
    default_session_id: uuid.UUID | None,
    target_chat_ids: list[uuid.UUID],
) -> None:
    if next_run_at is None:
        raise HTTPException(status_code=422, detail="Выберите дату отправки")
    if as_aware(next_run_at) <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Выберите будущую дату отправки")

    if schedule_kind == ScheduleKind.interval:
        if interval_minutes is None:
            raise HTTPException(status_code=422, detail="Укажите интервал повтора")
        if interval_minutes < 20:
            raise HTTPException(status_code=422, detail="Минимальный интервал повтора — 20 минут")
        if interval_minutes <= 30 and not spam_risk_acknowledged:
            raise HTTPException(
                status_code=422,
                detail="Подтвердите риск: за частую отправку сообщений Telegram может ограничить аккаунт",
            )
    elif schedule_kind == ScheduleKind.custom_weekdays:
        days = serialize_schedule_weekdays(schedule_weekdays)
        if not days:
            raise HTTPException(status_code=422, detail="Выберите хотя бы один день недели")

    if not default_session_id:
        raise HTTPException(status_code=422, detail="Сначала подключите Telegram-аккаунт")
    if not target_chat_ids:
        raise HTTPException(status_code=422, detail="Выберите хотя бы одну группу")
    if len(set(target_chat_ids)) > get_settings().max_targets_per_post:
        raise HTTPException(
            status_code=422,
            detail=f"Можно выбрать не больше {get_settings().max_targets_per_post} групп на один пост",
        )


def validate_owned_session_and_targets(
    *,
    telegram_user_id: int,
    session_id: uuid.UUID | None,
    target_chat_ids: list[uuid.UUID],
    db: Session,
) -> None:
    if session_id:
        session = db.get(TelegramSession, session_id)
        if (
            not session
            or session.owner_telegram_id != telegram_user_id
            or session.status != SessionStatus.active
        ):
            raise HTTPException(status_code=404, detail="Telegram account not found")

    for target_chat_id in target_chat_ids:
        target = db.get(TargetChat, target_chat_id)
        if not target or target.owner_telegram_id != telegram_user_id or not target.enabled:
            raise HTTPException(status_code=404, detail="Group not found")


def delete_session_files(session_path: str | None) -> None:
    if not session_path:
        return
    path = Path(session_path)
    for candidate in {path, path.with_suffix(".session"), path.with_suffix(".session-journal")}:
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def health() -> dict[str, object]:
    return {"ok": True, "env": get_settings().app_env}


def api_health() -> dict[str, object]:
    return health()


def app_config(telegram_user_id: int | None = Depends(optional_telegram_user_id)) -> AppConfigOut:
    logger.info(
        "Miniapp config requested: telegram_user_id=%s is_admin=%s",
        telegram_user_id,
        is_admin_id(telegram_user_id),
    )
    return AppConfigOut(
        bot_username=get_settings().bot_username,
        is_admin=is_admin_id(telegram_user_id),
    )


def get_user_settings(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> UserSettingsOut:
    return AccountService(db).user_settings(telegram_user_id=telegram_user_id)


def list_sessions(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[TelegramSession]:
    return AccountService(db).list_sessions(telegram_user_id=telegram_user_id)


async def start_account_login(
    payload: AccountStartLogin,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    settings = get_settings()
    check_rate_limit(
        db,
        scope="login:start",
        key=f"{telegram_user_id}:{normalize_phone_key(payload.phone)}",
        limit=RATE_LIMIT_LOGIN_START_ATTEMPTS,
        window_seconds=RATE_LIMIT_LOGIN_START_WINDOW_SECONDS,
    )
    safe_phone = phone_digits(payload.phone)
    session = find_session_by_phone(db, owner_telegram_id=telegram_user_id, phone=payload.phone)
    if not session:
        if user_sessions_count(db, telegram_user_id) >= settings.max_sessions_per_user:
            raise HTTPException(status_code=429, detail="Достигнут лимит Telegram-аккаунтов")
        session_name = unique_session_name(db, owner_telegram_id=telegram_user_id, safe_phone=safe_phone)
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
        db.add(session)
        db.flush()
    else:
        session.phone = payload.phone
        session.api_id = settings.telegram_api_id
        session.api_hash = settings.telegram_api_hash
        session_name = session.name or unique_session_name(db, owner_telegram_id=telegram_user_id, safe_phone=safe_phone)
        session_path = str(settings.telegram_sessions_dir / session_name)
        session.name = session.name or session_name
        session.session_path = session.session_path or session_path

    cooldown_seconds = remaining_login_code_cooldown(session)
    if cooldown_seconds:
        raise HTTPException(
            status_code=429,
            detail=f"Повторно запросить код можно через {cooldown_seconds} сек.",
        )
    db.commit()

    try:
        code_request = await request_login_code(session, force_sms=payload.force_sms)
    except Exception as exc:
        session.phone_code_hash = None
        db.commit()
        await raise_login_error("start-login", session, exc)

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
    db.commit()
    return AccountLoginOut(
        session_id=session.id,
        status=session.status,
        message=login_code_message(code_request.delivery_type, force_sms=payload.force_sms),
        delivery_type=code_request.delivery_type,
        next_delivery_type=code_request.next_delivery_type,
    )


async def confirm_account_code(
    payload: AccountCodeConfirm,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    session = TelegramSessionRepository(db).fetch_owned(payload.session_id, telegram_user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Telegram account not found")
    check_rate_limit(
        db,
        scope="login:code",
        key=str(session.id),
        limit=RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS,
        window_seconds=RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS,
    )

    try:
        completed, me = await confirm_login_code(session, payload.code)
    except Exception as exc:
        session.phone_code_hash = None
        db.commit()
        await raise_login_error("confirm-code", session, exc)

    if not completed:
        session.status = SessionStatus.password_needed
        db.commit()
        return AccountLoginOut(
            session_id=session.id,
            status=session.status,
            message="Two-step verification is enabled. Enter your Telegram password.",
        )

    session.telegram_user_id = me.id
    session.username = me.username
    session.status = SessionStatus.active
    session.phone_code_hash = None
    user_settings(telegram_user_id=telegram_user_id, db=db).autopost_paused = False
    db.commit()
    return AccountLoginOut(session_id=session.id, status=session.status, message="Account connected.")


async def confirm_account_password(
    payload: AccountPasswordConfirm,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    session = TelegramSessionRepository(db).fetch_owned(payload.session_id, telegram_user_id)
    if not session:
        raise HTTPException(status_code=404, detail="Telegram account not found")
    check_rate_limit(
        db,
        scope="login:password",
        key=str(session.id),
        limit=RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS,
        window_seconds=RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS,
    )

    try:
        me = await confirm_login_password(session, payload.password)
    except Exception as exc:
        session.phone_code_hash = None
        db.commit()
        await raise_login_error("confirm-password", session, exc)

    session.telegram_user_id = me.id
    session.username = me.username
    session.status = SessionStatus.active
    session.phone_code_hash = None
    user_settings(telegram_user_id=telegram_user_id, db=db).autopost_paused = False
    db.commit()
    return AccountLoginOut(session_id=session.id, status=session.status, message="Account connected.")


def cancel_user_pending_jobs(*, telegram_user_id: int, db: Session) -> int:
    return PublishJobRepository(db).cancel_pending_for_owner(telegram_user_id)


def pause_account(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountPauseOut:
    return AccountService(db).pause_autoposting(telegram_user_id=telegram_user_id)


def logout_account(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountPauseOut:
    return pause_account(telegram_user_id=telegram_user_id, db=db)


def resume_account(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountPauseOut:
    return AccountService(db).resume_autoposting(telegram_user_id=telegram_user_id)


async def revoke_account_session(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountRevokeOut:
    return await AccountService(db).revoke_account(
        telegram_user_id=telegram_user_id,
        logout_session=logout_session_from_telegram,
        delete_session_files=delete_session_files,
    )


async def sync_session_chats(
    session_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)
    return await ChatService(
        db=db,
        list_dialogs=list_dialogs_from_session,
        list_folders_from_session=list_dialog_folders_from_session,
        send_alert=send_alert,
    ).sync_session_chats(session_id=session_id, telegram_user_id=telegram_user_id)


def list_chats(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[TargetChat]:
    return ChatService(
        db=db,
        list_dialogs=list_dialogs_from_session,
        list_folders_from_session=list_dialog_folders_from_session,
        send_alert=send_alert,
    ).list_chats(telegram_user_id=telegram_user_id)


async def list_folders(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[DialogFolderOut]:
    return await ChatService(
        db=db,
        list_dialogs=list_dialogs_from_session,
        list_folders_from_session=list_dialog_folders_from_session,
        send_alert=send_alert,
    ).list_folders(telegram_user_id=telegram_user_id)


def create_chat(
    payload: TargetChatCreate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> TargetChat:
    raise HTTPException(
        status_code=410,
        detail="Ручное добавление групп отключено. Используйте синхронизацию чатов Telegram.",
    )


def list_posts(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[PostOut]:
    if not active_account(telegram_user_id=telegram_user_id, db=db):
        return []

    posts = PostRepository(db).list_for_owner(telegram_user_id)
    return [post_to_out(post) for post in posts]


def create_post(
    payload: PostCreate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)
    if payload.status == PostStatus.scheduled:
        enforce_active_post_limit(db, telegram_user_id)
        validate_post_schedule(
            schedule_kind=payload.schedule_kind,
            next_run_at=payload.next_run_at,
            interval_minutes=payload.interval_minutes,
            schedule_weekdays=payload.schedule_weekdays,
            spam_risk_acknowledged=payload.spam_risk_acknowledged,
            default_session_id=payload.default_session_id,
            target_chat_ids=payload.target_chat_ids,
        )

    validate_owned_session_and_targets(
        telegram_user_id=telegram_user_id,
        session_id=payload.default_session_id,
        target_chat_ids=payload.target_chat_ids,
        db=db,
    )

    post_data = payload.model_dump(
        exclude={"target_chat_ids", "spam_risk_acknowledged", "schedule_weekdays"}
    )
    post_data["schedule_weekdays"] = schedule_weekdays_for_storage(
        payload.schedule_kind,
        payload.schedule_weekdays,
    )
    post = Post(**post_data, created_by_telegram_id=telegram_user_id)
    db.add(post)
    db.flush()
    PostRepository(db).replace_targets(post, payload.target_chat_ids)
    db.commit()
    db.refresh(post)
    return post_to_out(post)


def schedule_post(
    post_id: uuid.UUID,
    payload: PostScheduleUpdate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    post = PostRepository(db).fetch_owned(post_id, telegram_user_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)
    enforce_active_post_limit(db, telegram_user_id, current_post=post)
    if len(post.media_items) > get_settings().max_media_items_per_post:
        raise HTTPException(status_code=422, detail="Слишком много медиа в одном посте")

    validate_post_schedule(
        schedule_kind=payload.schedule_kind,
        next_run_at=payload.next_run_at,
        interval_minutes=payload.interval_minutes,
        schedule_weekdays=payload.schedule_weekdays,
        spam_risk_acknowledged=payload.spam_risk_acknowledged,
        default_session_id=payload.default_session_id,
        target_chat_ids=payload.target_chat_ids,
    )
    validate_owned_session_and_targets(
        telegram_user_id=telegram_user_id,
        session_id=payload.default_session_id,
        target_chat_ids=payload.target_chat_ids,
        db=db,
    )

    post.status = PostStatus.scheduled
    post.schedule_kind = payload.schedule_kind
    post.next_run_at = payload.next_run_at
    post.interval_minutes = payload.interval_minutes
    post.schedule_weekdays = schedule_weekdays_for_storage(
        payload.schedule_kind,
        payload.schedule_weekdays,
    )
    post.timezone = payload.timezone
    post.default_session_id = payload.default_session_id
    cancel_pending_jobs(post, db)
    PostRepository(db).replace_targets(post, payload.target_chat_ids)
    db.commit()
    db.refresh(post)
    return post_to_out(post)


def pause_post(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    post = PostRepository(db).fetch_owned(post_id, telegram_user_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)
    if post.status not in {PostStatus.scheduled, PostStatus.paused}:
        raise HTTPException(status_code=409, detail="Можно поставить на паузу только пост из очереди")

    post.status = PostStatus.paused
    cancel_pending_jobs(post, db)
    db.commit()
    db.refresh(post)
    return post_to_out(post)


def resume_post(
    post_id: uuid.UUID,
    payload: PostResumeUpdate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    post = PostRepository(db).fetch_owned(post_id, telegram_user_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)
    if post.status != PostStatus.paused:
        raise HTTPException(status_code=409, detail="Пост не на паузе")

    next_run_at = payload.next_run_at or post.next_run_at
    if next_run_at is None or as_aware(next_run_at) <= datetime.now(UTC):
        raise HTTPException(status_code=422, detail="Выберите новую будущую дату отправки")

    post.next_run_at = next_run_at
    post.status = PostStatus.scheduled
    db.commit()
    db.refresh(post)
    return post_to_out(post)


async def delete_post(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> DeletePostOut:
    post = PostRepository(db).fetch_owned(post_id, telegram_user_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)

    message_refs = collect_source_message_refs(post)
    match_texts = {post.body}
    created_at = post.created_at
    media_count = len(post.media_items)
    deleted_jobs = PublishJobRepository(db).delete_for_post(post.id)
    PostRepository(db).delete(post)
    db.commit()
    telegram_delete = await delete_source_messages(
        telegram_user_id=telegram_user_id,
        refs=message_refs,
        db=db,
        match_texts=match_texts,
        ack_text=POST_SAVED_ACK_TEXT,
        created_at=created_at,
        media_count=media_count,
    )

    return DeletePostOut(
        ok=True,
        deleted_jobs=deleted_jobs,
        source_messages_found=len(message_refs),
        telegram_delete_attempted=telegram_delete.attempted,
        deleted_bot_messages=telegram_delete.deleted,
        telegram_delete_errors=telegram_delete.errors,
    )


def enqueue_now(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    post = PostRepository(db).fetch_owned(post_id, telegram_user_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
    require_autopost_enabled(telegram_user_id=telegram_user_id, db=db)
    if len({target.target_chat_id for target in post.targets}) > get_settings().max_targets_per_post:
        raise HTTPException(
            status_code=422,
            detail=f"Можно выбрать не больше {get_settings().max_targets_per_post} групп на один пост",
        )
    enforce_daily_job_creation_limit(db, telegram_user_id, len(post.targets))

    count = 0
    publish_jobs = PublishJobRepository(db)
    for target in post.targets:
        if publish_jobs.active_for_post_target(post_id=post.id, target_chat_id=target.target_chat_id):
            continue
        publish_jobs.add_pending(
            post_id=post.id,
            target_chat_id=target.target_chat_id,
            session_id=post.default_session_id,
            due_at=post.next_run_at or post.created_at,
        )
        count += 1
    db.commit()
    return {"ok": True, "jobs_created": count}


def list_jobs(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[PublishJob]:
    if not active_account(telegram_user_id=telegram_user_id, db=db):
        return []

    return PublishJobRepository(db).list_recent_for_owner(telegram_user_id, limit=100)


def list_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AuditPageOut:
    return audit_page_for_user(db, telegram_user_id=telegram_user_id, page=page, page_size=page_size)


def audit_page_for_user(db: Session, *, telegram_user_id: int, page: int, page_size: int) -> AuditPageOut:
    return AuditService(db=db, fetch_message=get_message_from_session, send_alert=send_alert).audit_page_for_user(
        telegram_user_id=telegram_user_id,
        page=page,
        page_size=page_size,
    )


async def get_audit_message(
    job_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AuditMessageOut:
    return await audit_message_for_user(db, telegram_user_id=telegram_user_id, job_id=job_id)


async def audit_message_for_user(db: Session, *, telegram_user_id: int, job_id: uuid.UUID) -> AuditMessageOut:
    return await AuditService(
        db=db,
        fetch_message=get_message_from_session,
        send_alert=send_alert,
    ).audit_message_for_user(
        telegram_user_id=telegram_user_id,
        job_id=job_id,
    )


def admin_list_user_audit(
    telegram_user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    _admin_id: int = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AuditPageOut:
    return audit_page_for_user(db, telegram_user_id=telegram_user_id, page=page, page_size=page_size)


async def admin_get_user_audit_message(
    telegram_user_id: int,
    job_id: uuid.UUID,
    _admin_id: int = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AuditMessageOut:
    return await audit_message_for_user(db, telegram_user_id=telegram_user_id, job_id=job_id)


def admin_user_out(db: Session, telegram_user_id: int) -> AdminUserOut:
    return AdminService(db).admin_user_out(telegram_user_id)


def admin_list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query: str = "",
    _admin_id: int = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserPageOut:
    return AdminService(db).list_users(page=page, page_size=page_size, query=query)


def admin_update_user(
    telegram_user_id: int,
    payload: AdminUserUpdate,
    _admin_id: int = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    return AdminService(db).update_user(telegram_user_id, payload)


def admin_stats(
    _admin_id: int = Depends(require_admin_user),
    db: Session = Depends(get_db),
) -> AdminStatsOut:
    return AdminService(db).stats()


def _create_application() -> FastAPI:
    from autopost_manager.api_routes.application import create_application

    return create_application()


app = _create_application()


def main() -> None:
    uvicorn.run("autopost_manager.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
