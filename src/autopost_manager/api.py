from __future__ import annotations

import uuid
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from autopost_manager.config import get_settings
from autopost_manager.db import create_schema, get_db
from autopost_manager.models import (
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
    JobOut,
    PostCreate,
    PostMediaOut,
    PostOut,
    PostScheduleUpdate,
    TargetChatCreate,
    TargetChatOut,
    TelegramSessionOut,
)
from autopost_manager.security import require_user
from autopost_manager.telegram_client import (
    confirm_login_code,
    confirm_login_password,
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


def validate_post_schedule(
    *,
    schedule_kind: ScheduleKind,
    interval_minutes: int | None,
    spam_risk_acknowledged: bool,
    default_session_id: uuid.UUID | None,
    target_chat_ids: list[uuid.UUID],
) -> None:
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
        if not session or session.owner_telegram_id != telegram_user_id:
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
            api_id=payload.api_id,
            api_hash=payload.api_hash,
            session_path=session_path,
            status=SessionStatus.credentials_needed,
            min_send_interval_seconds=settings.default_min_send_interval_seconds,
        )
        db.add(session)
        db.flush()
    else:
        session.api_id = payload.api_id
        session.api_hash = payload.api_hash
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
        delete_session_files(session.session_path)

    for chat in chats:
        chat.enabled = False

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

    validate_post_schedule(
        schedule_kind=payload.schedule_kind,
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
    post.targets.clear()
    db.flush()
    for target_chat_id in payload.target_chat_ids:
        db.add(PostTarget(post_id=post.id, target_chat_id=target_chat_id))
    db.commit()
    db.refresh(post)
    return post_to_out(post)


@app.post("/api/posts/{post_id}/enqueue-now")
def enqueue_now(
    post_id: uuid.UUID,
    telegram_user_id: int = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    post = db.get(Post, post_id)
    if not post or post.created_by_telegram_id != telegram_user_id:
        raise HTTPException(status_code=404, detail="Post not found")

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
    return list(
        db.scalars(
            select(PublishJob)
            .join(Post, PublishJob.post_id == Post.id)
            .where(Post.created_by_telegram_id == telegram_user_id)
            .order_by(PublishJob.created_at.desc())
            .limit(100)
        )
    )


def main() -> None:
    uvicorn.run("autopost_manager.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
