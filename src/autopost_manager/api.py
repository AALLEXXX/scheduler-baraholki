from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import uuid
from pathlib import Path

import uvicorn
from aiogram import Bot
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autopost_manager.config import get_settings
from autopost_manager.db import create_schema, get_db
from autopost_manager.messages import POST_SAVED_ACK_TEXT
from autopost_manager.models import (
    JobStatus,
    Post,
    PostStatus,
    PostTarget,
    PublishJob,
    ScheduleKind,
    SessionStatus,
    TargetChat,
    TargetChatType,
    TelegramSession,
)
from autopost_manager.schemas import (
    AccountCodeConfirm,
    AccountLoginOut,
    AccountLogoutOut,
    AccountPasswordConfirm,
    AccountStartLogin,
    AppConfigOut,
    AuditItemOut,
    AuditPageOut,
    DeletePostOut,
    DialogFolderOut,
    JobOut,
    PostCreate,
    PostMediaOut,
    PostOut,
    PostResumeUpdate,
    PostScheduleUpdate,
    TargetChatCreate,
    TargetChatOut,
    TelegramSessionOut,
)
from autopost_manager.security import require_user
from autopost_manager.telegram_client import (
    confirm_login_code,
    confirm_login_password,
    delete_messages_from_session,
    list_dialog_folders_from_session,
    list_dialogs_from_session,
    request_login_code,
)

app = FastAPI(title="Autopost Manager")


@app.on_event("startup")
def startup() -> None:
    create_schema()
    get_settings().telegram_sessions_dir.mkdir(parents=True, exist_ok=True)


miniapp_dir = get_settings().miniapp_dir
if miniapp_dir.exists():
    app.mount("/miniapp", StaticFiles(directory=miniapp_dir, html=True), name="miniapp")


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


def cancel_pending_jobs(post: Post, db: Session) -> int:
    jobs = list(
        db.scalars(
            select(PublishJob)
            .where(PublishJob.post_id == post.id)
            .where(PublishJob.status == JobStatus.pending)
        )
    )
    for job in jobs:
        job.status = JobStatus.cancelled
    return len(jobs)


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

    if not default_session_id:
        raise HTTPException(status_code=422, detail="Сначала подключите Telegram-аккаунт")
    if not target_chat_ids:
        raise HTTPException(status_code=422, detail="Выберите хотя бы одну группу")


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


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "env": get_settings().app_env}


@app.get("/api/health")
def api_health() -> dict[str, object]:
    return health()


@app.get("/api/app-config", response_model=AppConfigOut)
def app_config() -> AppConfigOut:
    return AppConfigOut(bot_username=get_settings().bot_username)


@app.get("/api/sessions", response_model=list[TelegramSessionOut])
def list_sessions(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[TelegramSession]:
    return list(
        db.scalars(
            select(TelegramSession)
            .where(TelegramSession.owner_telegram_id == telegram_user_id)
            .order_by(TelegramSession.created_at.desc())
        )
    )


@app.post("/api/account/start-login", response_model=AccountLoginOut)
async def start_account_login(
    payload: AccountStartLogin,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    settings = get_settings()
    safe_phone = "".join(ch for ch in payload.phone if ch.isdigit())
    session_name = f"tg_{telegram_user_id}_{safe_phone[-8:] or 'account'}"
    session_path = str(settings.telegram_sessions_dir / session_name)

    session = db.scalars(
        select(TelegramSession)
        .where(TelegramSession.owner_telegram_id == telegram_user_id)
        .where(TelegramSession.phone == payload.phone)
    ).first()
    if not session:
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
        session.api_id = settings.telegram_api_id
        session.api_hash = settings.telegram_api_hash
        session.session_path = session.session_path or session_path

    try:
        session.phone_code_hash = await request_login_code(session)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Could not send Telegram code: {exc}") from exc

    session.status = SessionStatus.code_needed
    db.commit()
    return AccountLoginOut(
        session_id=session.id,
        status=session.status,
        message="Telegram sent a login code. Enter it below.",
    )


@app.post("/api/account/confirm-code", response_model=AccountLoginOut)
async def confirm_account_code(
    payload: AccountCodeConfirm,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    session = db.get(TelegramSession, payload.session_id)
    if not session or session.owner_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Telegram account not found")

    try:
        completed, me = await confirm_login_code(session, payload.code)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not confirm code: {exc}") from exc

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
    db.commit()
    return AccountLoginOut(session_id=session.id, status=session.status, message="Account connected.")


@app.post("/api/account/confirm-password", response_model=AccountLoginOut)
async def confirm_account_password(
    payload: AccountPasswordConfirm,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLoginOut:
    session = db.get(TelegramSession, payload.session_id)
    if not session or session.owner_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Telegram account not found")

    try:
        me = await confirm_login_password(session, payload.password)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not confirm password: {exc}") from exc

    session.telegram_user_id = me.id
    session.username = me.username
    session.status = SessionStatus.active
    session.phone_code_hash = None
    db.commit()
    return AccountLoginOut(session_id=session.id, status=session.status, message="Account connected.")


@app.post("/api/account/logout", response_model=AccountLogoutOut)
def logout_account(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AccountLogoutOut:
    sessions = list(
        db.scalars(
            select(TelegramSession)
            .where(TelegramSession.owner_telegram_id == telegram_user_id)
            .where(TelegramSession.status != SessionStatus.revoked)
        )
    )
    chats = list(
        db.scalars(
            select(TargetChat)
            .where(TargetChat.owner_telegram_id == telegram_user_id)
            .where(TargetChat.enabled.is_(True))
        )
    )

    for session in sessions:
        session.status = SessionStatus.revoked
        session.phone_code_hash = None
        session.session_string = None
        delete_session_files(session.session_path)

    for chat in chats:
        chat.enabled = False

    posts = list(
        db.scalars(
            select(Post).where(Post.created_by_telegram_id == telegram_user_id)
        ).unique()
    )
    for post in posts:
        if post.status == PostStatus.scheduled:
            post.status = PostStatus.paused
        cancel_pending_jobs(post, db)

    db.commit()
    return AccountLogoutOut(revoked_sessions=len(sessions), disabled_chats=len(chats))


@app.post("/api/sessions/{session_id}/sync-chats")
async def sync_session_chats(
    session_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    sender_session = db.get(TelegramSession, session_id)
    if not sender_session or sender_session.owner_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Telegram account not found")

    try:
        dialogs = await list_dialogs_from_session(sender_session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    imported = 0
    for dialog in dialogs:
        existing = db.scalars(
            select(TargetChat)
            .where(TargetChat.session_id == sender_session.id)
            .where(TargetChat.telegram_chat_id == dialog["telegram_chat_id"])
        ).first()
        chat_type = TargetChatType.channel if dialog["is_channel"] and not dialog["is_group"] else TargetChatType.supergroup
        if existing:
            existing.title = str(dialog["title"])
            existing.username = dialog["username"] if dialog["username"] else None
            existing.type = chat_type
            existing.enabled = True
        else:
            db.add(
                TargetChat(
                    owner_telegram_id=telegram_user_id,
                    session_id=sender_session.id,
                    telegram_chat_id=int(dialog["telegram_chat_id"]),
                    title=str(dialog["title"]),
                    username=dialog["username"] if dialog["username"] else None,
                    type=chat_type,
                    enabled=True,
                )
            )
            imported += 1
    db.commit()
    return {"imported": imported, "total_dialogs": len(dialogs)}


@app.get("/api/chats", response_model=list[TargetChatOut])
def list_chats(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[TargetChat]:
    return list(
        db.scalars(
            select(TargetChat)
            .where(TargetChat.owner_telegram_id == telegram_user_id)
            .where(TargetChat.enabled.is_(True))
            .order_by(TargetChat.title)
        )
    )


@app.get("/api/folders", response_model=list[DialogFolderOut])
async def list_folders(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[DialogFolderOut]:
    session = db.scalars(
        select(TelegramSession)
        .where(TelegramSession.owner_telegram_id == telegram_user_id)
        .where(TelegramSession.status == SessionStatus.active)
        .order_by(TelegramSession.updated_at.desc())
    ).first()
    if not session:
        return []

    try:
        folders = await list_dialog_folders_from_session(session)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()

    enabled_chat_ids = set(
        db.scalars(
            select(TargetChat.telegram_chat_id)
            .where(TargetChat.owner_telegram_id == telegram_user_id)
            .where(TargetChat.enabled.is_(True))
        )
    )
    rows: list[DialogFolderOut] = []
    for folder in folders:
        chat_ids = [
            int(chat_id)
            for chat_id in folder["telegram_chat_ids"]
            if int(chat_id) in enabled_chat_ids
        ]
        if chat_ids:
            rows.append(
                DialogFolderOut(
                    id=int(folder["id"]),
                    title=str(folder["title"]),
                    telegram_chat_ids=chat_ids,
                )
            )
    return rows


@app.post("/api/chats", response_model=TargetChatOut)
def create_chat(
    payload: TargetChatCreate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> TargetChat:
    if payload.session_id:
        session = db.get(TelegramSession, payload.session_id)
        if not session or session.owner_telegram_id != telegram_user_id:
            raise HTTPException(status_code=404, detail="Telegram account not found")

    existing = db.scalars(
        select(TargetChat)
        .where(TargetChat.session_id == payload.session_id)
        .where(TargetChat.owner_telegram_id == telegram_user_id)
        .where(TargetChat.telegram_chat_id == payload.telegram_chat_id)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This destination group is already added")

    chat = TargetChat(**payload.model_dump(), owner_telegram_id=telegram_user_id)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@app.get("/api/posts", response_model=list[PostOut])
def list_posts(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[PostOut]:
    if not active_account(telegram_user_id=telegram_user_id, db=db):
        return []

    posts = (
        db.scalars(
            select(Post)
            .where(Post.created_by_telegram_id == telegram_user_id)
            .order_by(Post.created_at.desc())
        )
        .unique()
        .all()
    )
    return [post_to_out(post) for post in posts]


@app.post("/api/posts", response_model=PostOut)
def create_post(
    payload: PostCreate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    if payload.status == PostStatus.scheduled:
        validate_post_schedule(
            schedule_kind=payload.schedule_kind,
            next_run_at=payload.next_run_at,
            interval_minutes=payload.interval_minutes,
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

    post_data = payload.model_dump(exclude={"target_chat_ids", "spam_risk_acknowledged"})
    post = Post(**post_data, created_by_telegram_id=telegram_user_id)
    db.add(post)
    db.flush()
    for target_chat_id in payload.target_chat_ids:
        db.add(PostTarget(post_id=post.id, target_chat_id=target_chat_id))
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@app.post("/api/posts/{post_id}/schedule", response_model=PostOut)
def schedule_post(
    post_id: uuid.UUID,
    payload: PostScheduleUpdate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    post = db.get(Post, post_id)
    if not post or post.created_by_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)

    validate_post_schedule(
        schedule_kind=payload.schedule_kind,
        next_run_at=payload.next_run_at,
        interval_minutes=payload.interval_minutes,
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
    post.timezone = payload.timezone
    post.default_session_id = payload.default_session_id
    cancel_pending_jobs(post, db)
    post.targets.clear()
    db.flush()
    for target_chat_id in payload.target_chat_ids:
        db.add(PostTarget(post_id=post.id, target_chat_id=target_chat_id))
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@app.patch("/api/posts/{post_id}/pause", response_model=PostOut)
def pause_post(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    post = db.get(Post, post_id)
    if not post or post.created_by_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
    if post.status not in {PostStatus.scheduled, PostStatus.paused}:
        raise HTTPException(status_code=409, detail="Можно поставить на паузу только пост из очереди")

    post.status = PostStatus.paused
    cancel_pending_jobs(post, db)
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@app.patch("/api/posts/{post_id}/resume", response_model=PostOut)
def resume_post(
    post_id: uuid.UUID,
    payload: PostResumeUpdate,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> PostOut:
    post = db.get(Post, post_id)
    if not post or post.created_by_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)
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


@app.delete("/api/posts/{post_id}", response_model=DeletePostOut)
async def delete_post(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> DeletePostOut:
    post = db.get(Post, post_id)
    if not post or post.created_by_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)

    message_refs = collect_source_message_refs(post)
    match_texts = {post.body}
    created_at = post.created_at
    media_count = len(post.media_items)
    jobs = list(db.scalars(select(PublishJob).where(PublishJob.post_id == post.id)))
    for job in jobs:
        db.delete(job)
    db.delete(post)
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
        deleted_jobs=len(jobs),
        source_messages_found=len(message_refs),
        telegram_delete_attempted=telegram_delete.attempted,
        deleted_bot_messages=telegram_delete.deleted,
        telegram_delete_errors=telegram_delete.errors,
    )


@app.post("/api/posts/{post_id}/enqueue-now")
def enqueue_now(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    post = db.get(Post, post_id)
    if not post or post.created_by_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Post not found")
    require_active_account(telegram_user_id=telegram_user_id, db=db)

    count = 0
    for target in post.targets:
        db.add(
            PublishJob(
                post_id=post.id,
                target_chat_id=target.target_chat_id,
                session_id=post.default_session_id,
                due_at=post.next_run_at or post.created_at,
            )
        )
        count += 1
    db.commit()
    return {"ok": True, "jobs_created": count}


@app.get("/api/jobs", response_model=list[JobOut])
def list_jobs(
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> list[PublishJob]:
    if not active_account(telegram_user_id=telegram_user_id, db=db):
        return []

    return list(
        db.scalars(
            select(PublishJob)
            .join(Post, PublishJob.post_id == Post.id)
            .where(Post.created_by_telegram_id == telegram_user_id)
            .order_by(PublishJob.created_at.desc())
            .limit(100)
        )
    )


@app.get("/api/audit", response_model=AuditPageOut)
def list_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> AuditPageOut:
    if not active_account(telegram_user_id=telegram_user_id, db=db):
        return AuditPageOut(items=[], page=page, page_size=page_size, total=0)

    base_query = (
        select(PublishJob, Post, TargetChat)
        .join(Post, PublishJob.post_id == Post.id)
        .join(TargetChat, PublishJob.target_chat_id == TargetChat.id)
        .where(Post.created_by_telegram_id == telegram_user_id)
    )
    total = db.scalar(
        select(func.count())
        .select_from(PublishJob)
        .join(Post, PublishJob.post_id == Post.id)
        .where(Post.created_by_telegram_id == telegram_user_id)
    )
    rows = db.execute(
        base_query.order_by(PublishJob.updated_at.desc(), PublishJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return AuditPageOut(
        items=[
            AuditItemOut(
                id=job.id,
                post_id=post.id,
                post_title=post.title,
                post_preview=post.body,
                media_count=len(post.media_items),
                target_chat_id=chat.id,
                target_chat_title=chat.title,
                due_at=job.due_at,
                updated_at=job.updated_at,
                status=job.status,
                attempts=job.attempts,
                telegram_message_id=job.telegram_message_id,
                last_error=job.last_error,
            )
            for job, post, chat in rows
        ],
        page=page,
        page_size=page_size,
        total=total or 0,
    )


def main() -> None:
    uvicorn.run("autopost_manager.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
