from __future__ import annotations

import uuid
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from autopost_manager.config import get_settings
from autopost_manager.db import create_schema, get_db
from autopost_manager.models import Post, PostTarget, PublishJob, TargetChat, TelegramSession
from autopost_manager.schemas import (
    JobOut,
    PostCreate,
    PostOut,
    TargetChatCreate,
    TargetChatOut,
    TelegramSessionOut,
)
from autopost_manager.security import require_admin

app = FastAPI(title="Autopost Manager")


@app.on_event("startup")
def startup() -> None:
    create_schema()
    get_settings().telegram_sessions_dir.mkdir(parents=True, exist_ok=True)


miniapp_dir = get_settings().miniapp_dir
if miniapp_dir.exists():
    app.mount("/miniapp", StaticFiles(directory=miniapp_dir, html=True), name="miniapp")


@app.get("/health")
def health() -> dict[str, object]:
    return {"ok": True, "env": get_settings().app_env}


@app.get("/api/sessions", response_model=list[TelegramSessionOut])
def list_sessions(
    _: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[TelegramSession]:
    return list(db.scalars(select(TelegramSession).order_by(TelegramSession.created_at.desc())))


@app.get("/api/chats", response_model=list[TargetChatOut])
def list_chats(
    _: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[TargetChat]:
    return list(db.scalars(select(TargetChat).order_by(TargetChat.title)))


@app.post("/api/chats", response_model=TargetChatOut)
def create_chat(
    payload: TargetChatCreate,
    _: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TargetChat:
    chat = TargetChat(**payload.model_dump())
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@app.get("/api/posts", response_model=list[PostOut])
def list_posts(
    _: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[PostOut]:
    posts = db.scalars(select(Post).order_by(Post.created_at.desc())).unique().all()
    return [
        PostOut(
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
        )
        for post in posts
    ]


@app.post("/api/posts", response_model=PostOut)
def create_post(
    payload: PostCreate,
    admin_telegram_id: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> PostOut:
    post_data = payload.model_dump(exclude={"target_chat_ids"})
    post = Post(**post_data, created_by_telegram_id=admin_telegram_id)
    db.add(post)
    db.flush()
    for target_chat_id in payload.target_chat_ids:
        db.add(PostTarget(post_id=post.id, target_chat_id=target_chat_id))
    db.commit()
    db.refresh(post)
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
        target_chat_ids=payload.target_chat_ids,
    )


@app.post("/api/posts/{post_id}/enqueue-now")
def enqueue_now(
    post_id: uuid.UUID,
    _: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    post = db.get(Post, post_id)
    if not post:
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
    _: int = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[PublishJob]:
    return list(db.scalars(select(PublishJob).order_by(PublishJob.created_at.desc()).limit(100)))


def main() -> None:
    uvicorn.run("autopost_manager.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
