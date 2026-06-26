from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
import logging
import uuid
from pathlib import Path

import uvicorn
from aiogram import Bot
from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session
from autopost_manager.alerts import send_alert
from autopost_manager import api_runtime
from autopost_manager.config import get_settings
from autopost_manager.db import get_db
from autopost_manager.messages import POST_SAVED_ACK_TEXT
from autopost_manager.models import (
    Post,
    PostStatus,
    PublishJob,
    ScheduleKind,
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
    PostOut,
    PostResumeUpdate,
    PostScheduleUpdate,
    TargetChatCreate,
    UserSettingsOut,
)
from autopost_manager.repositories.target_chats import TargetChatRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.posts import PostRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.repositories.user_settings import UserSettingsRepository
from autopost_manager.security import require_user, verify_webapp_init_data
from autopost_manager.services.admin import AdminService
from autopost_manager.services.admin import day_start as admin_day_start
from autopost_manager.services.admin import failed_total as admin_failed_total
from autopost_manager.services.admin import mask_phone as admin_mask_phone
from autopost_manager.services.admin import sent_since as admin_sent_since
from autopost_manager.services.audit import AuditService
from autopost_manager.services.audit import telegram_message_link as audit_telegram_message_link
from autopost_manager.services.account import AccountService
from autopost_manager.services.account import login_code_message as account_login_code_message
from autopost_manager.services.account import login_error_detail as account_login_error_detail
from autopost_manager.services.account import normalize_phone_key as account_normalize_phone_key
from autopost_manager.services.account import phone_digits as account_phone_digits
from autopost_manager.services.account import remaining_login_code_cooldown as account_remaining_login_code_cooldown
from autopost_manager.services.chats import ChatService
from autopost_manager.services.posts import PostService
from autopost_manager.services.posts import as_aware as post_as_aware
from autopost_manager.services.posts import parse_schedule_weekdays as post_parse_schedule_weekdays
from autopost_manager.services.posts import post_to_out as service_post_to_out
from autopost_manager.services.posts import schedule_weekdays_for_storage as post_schedule_weekdays_for_storage
from autopost_manager.services.posts import serialize_schedule_weekdays as post_serialize_schedule_weekdays
from autopost_manager.services.telegram_cleanup import BotMessageDeleteResult
from autopost_manager.services.telegram_cleanup import TelegramCleanupService
from autopost_manager.services.telegram_cleanup import collect_source_message_refs as service_collect_source_message_refs
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
alert_unhandled_errors = api_runtime.alert_unhandled_errors
lifespan = api_runtime.lifespan
request_user_id = api_runtime.request_user_id
security_headers = api_runtime.security_headers
startup = api_runtime.startup
validate_runtime_settings = api_runtime.validate_runtime_settings

LOGIN_CODE_COOLDOWN_SECONDS = 90
RATE_LIMIT_LOGIN_START_WINDOW_SECONDS = 10 * 60
RATE_LIMIT_LOGIN_CONFIRM_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_LOGIN_START_ATTEMPTS = 3
RATE_LIMIT_LOGIN_CONFIRM_ATTEMPTS = 5


def login_error_detail(stage: str, exc: Exception) -> str:
    return account_login_error_detail(stage, exc)


def login_code_message(delivery_type: str | None, *, force_sms: bool) -> str:
    return account_login_code_message(delivery_type, force_sms=force_sms)


def remaining_login_code_cooldown(session: TelegramSession) -> int:
    return account_remaining_login_code_cooldown(session)


async def raise_login_error(stage: str, session: TelegramSession, exc: Exception) -> None:
    await AccountService(db=None).raise_login_error(
        stage=stage,
        session=session,
        exc=exc,
        send_alert=send_alert,
    )


def post_to_out(post: Post) -> PostOut:
    return service_post_to_out(post)


def collect_source_message_refs(post: Post) -> set[tuple[int, int]]:
    return service_collect_source_message_refs(post)


def as_aware(value: datetime) -> datetime:
    return post_as_aware(value)


def parse_schedule_weekdays(value: str | None) -> list[int]:
    return post_parse_schedule_weekdays(value)


def serialize_schedule_weekdays(values: list[int] | None) -> str | None:
    return post_serialize_schedule_weekdays(values)


def schedule_weekdays_for_storage(
    schedule_kind: ScheduleKind,
    values: list[int] | None,
) -> str | None:
    if schedule_kind != ScheduleKind.custom_weekdays:
        return None
    return post_schedule_weekdays_for_storage(schedule_kind, values)


def cancel_pending_jobs(post: Post, db: Session) -> int:
    return PublishJobRepository(db).cancel_pending_for_post(post.id)


def active_account(
    *,
    telegram_user_id: int,
    db: Session,
) -> TelegramSession | None:
    return TelegramSessionRepository(db).active_for_owner(telegram_user_id)


def telegram_message_link(chat: TargetChat, message_id: int | None) -> str | None:
    return audit_telegram_message_link(chat, message_id)


def user_settings(
    *,
    telegram_user_id: int,
    db: Session,
) -> UserSettings:
    return UserSettingsRepository(db).get_or_create(telegram_user_id)


def autopost_paused(
    *,
    telegram_user_id: int,
    db: Session,
) -> bool:
    settings = UserSettingsRepository(db).fetch_by_user_id(telegram_user_id)
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
    AccountService(db).check_rate_limit(
        scope=scope,
        key=key,
        limit=limit,
        window_seconds=window_seconds,
    )


def normalize_phone_key(phone: str) -> str:
    return account_normalize_phone_key(phone)


def phone_digits(phone: str | None) -> str:
    return account_phone_digits(phone)


def find_session_by_phone(db: Session, *, owner_telegram_id: int, phone: str) -> TelegramSession | None:
    return AccountService(db).find_session_by_phone(owner_telegram_id=owner_telegram_id, phone=phone)


def unique_session_name(db: Session, *, owner_telegram_id: int, safe_phone: str) -> str:
    return AccountService(db).unique_session_name(owner_telegram_id=owner_telegram_id, safe_phone=safe_phone)


def sent_since(db: Session, *, telegram_user_id: int | None = None, since: datetime | None = None) -> int:
    return admin_sent_since(db, telegram_user_id=telegram_user_id, since=since)


def failed_total(db: Session, *, telegram_user_id: int | None = None) -> int:
    return admin_failed_total(db, telegram_user_id=telegram_user_id)


def require_autopost_enabled(
    *,
    telegram_user_id: int,
    db: Session,
) -> None:
    settings = UserSettingsRepository(db).fetch_by_user_id(telegram_user_id)
    if settings and settings.banned:
        raise HTTPException(status_code=403, detail="Пользователь заблокирован администратором")
    if settings and settings.autopost_paused:
        raise HTTPException(status_code=409, detail="Автопостинг на паузе")
    if (
        settings
        and settings.daily_send_limit is not None
        and sent_since(db, telegram_user_id=telegram_user_id, since=day_start())
        >= settings.daily_send_limit
    ):
        raise HTTPException(status_code=429, detail="Достигнут дневной лимит отправки постов")


def active_scheduled_posts_count(db: Session, telegram_user_id: int) -> int:
    return PostRepository(db).count_active_scheduled_for_owner(telegram_user_id)


def user_sessions_count(db: Session, telegram_user_id: int) -> int:
    return TelegramSessionRepository(db).count_non_revoked_for_owner(telegram_user_id)


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
    settings = get_settings()
    return await TelegramCleanupService(
        db=None,
        bot_token=settings.bot_token,
        bot_username=settings.bot_username,
        send_alert=send_alert,
        delete_messages_from_session=delete_messages_from_session,
        bot_factory=Bot,
    ).delete_bot_messages(refs)


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
    settings = get_settings()
    return await TelegramCleanupService(
        db=db,
        bot_token=settings.bot_token,
        bot_username=settings.bot_username,
        send_alert=send_alert,
        delete_messages_from_session=delete_messages_from_session,
        bot_factory=Bot,
    ).delete_source_messages(
        telegram_user_id=telegram_user_id,
        refs=refs,
        delete_bot_messages=delete_bot_messages,
        match_texts=match_texts,
        ack_text=ack_text,
        created_at=created_at,
        media_count=media_count,
    )


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
        session = TelegramSessionRepository(db).fetch_owned_active(session_id, telegram_user_id)
        if not session:
            raise HTTPException(status_code=404, detail="Telegram account not found")

    for target_chat_id in target_chat_ids:
        target = TargetChatRepository(db).fetch_owned_enabled(target_chat_id, telegram_user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Group not found")


def delete_session_files(session_path: str | None) -> None:
    if not session_path:
        return
    path = Path(session_path)
    for candidate in {path, path.with_suffix(".session"), path.with_suffix(".session-journal")}:
        with suppress(OSError):
            candidate.unlink(missing_ok=True)


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
    return await AccountService(db).start_login(
        payload=payload,
        telegram_user_id=telegram_user_id,
        settings=get_settings(),
        request_login_code=request_login_code,
        send_alert=send_alert,
    )


async def confirm_account_code(
    payload: AccountCodeConfirm,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    return await AccountService(db).confirm_code(
        payload=payload,
        telegram_user_id=telegram_user_id,
        confirm_login_code=confirm_login_code,
        send_alert=send_alert,
    )


async def confirm_account_password(
    payload: AccountPasswordConfirm,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    return await AccountService(db).confirm_password(
        payload=payload,
        telegram_user_id=telegram_user_id,
        confirm_login_password=confirm_login_password,
        send_alert=send_alert,
    )


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
    return PostService(db=db, settings=get_settings()).list_posts(telegram_user_id=telegram_user_id)


def create_post(
    payload: PostCreate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    return PostService(db=db, settings=get_settings()).create_post(
        payload=payload,
        telegram_user_id=telegram_user_id,
    )


def schedule_post(
    post_id: uuid.UUID,
    payload: PostScheduleUpdate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    return PostService(db=db, settings=get_settings()).schedule_post(
        post_id=post_id,
        payload=payload,
        telegram_user_id=telegram_user_id,
    )


def pause_post(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    return PostService(db=db, settings=get_settings()).pause_post(
        post_id=post_id,
        telegram_user_id=telegram_user_id,
    )


def resume_post(
    post_id: uuid.UUID,
    payload: PostResumeUpdate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    return PostService(db=db, settings=get_settings()).resume_post(
        post_id=post_id,
        payload=payload,
        telegram_user_id=telegram_user_id,
    )


async def delete_post(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> DeletePostOut:
    return await PostService(db=db, settings=get_settings()).delete_post(
        post_id=post_id,
        telegram_user_id=telegram_user_id,
        delete_source_messages=delete_source_messages,
        ack_text=POST_SAVED_ACK_TEXT,
    )


def enqueue_now(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return PostService(db=db, settings=get_settings()).enqueue_now(
        post_id=post_id,
        telegram_user_id=telegram_user_id,
    )


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


def _create_application():
    from autopost_manager.api_routes.application import create_application

    return create_application()


app = _create_application()


def main() -> None:
    uvicorn.run("autopost_manager.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
