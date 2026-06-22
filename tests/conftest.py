from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

TEST_DB_PATH = Path("/tmp/autopost_manager_pytest.sqlite")
TEST_DB_PATH.unlink(missing_ok=True)

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_BASE_URL", "http://testserver")
os.environ.setdefault("MINI_APP_URL", "http://testserver/miniapp/")
os.environ.setdefault("MINIAPP_DIR", str(Path.cwd() / "miniapp"))
os.environ.setdefault("APP_SECRET", "test-app-secret-value")
os.environ.setdefault("BOT_TOKEN", "1234567890:TEST_BOT_TOKEN_VALUE")
os.environ.setdefault("TELEGRAM_API_ID", "123456")
os.environ.setdefault("TELEGRAM_API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("TELEGRAM_SESSIONS_DIR", "/tmp/autopost_manager_sessions")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{TEST_DB_PATH}")

from autopost_manager import api as api_module  # noqa: E402
from autopost_manager.db import Base, SessionLocal, engine  # noqa: E402
from autopost_manager.models import (  # noqa: E402
    JobStatus,
    Post,
    PostMedia,
    PostStatus,
    PostTarget,
    PublishJob,
    ScheduleKind,
    SessionStatus,
    TargetChat,
    TargetChatType,
    TelegramSession,
)


@pytest.fixture(autouse=True)
def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client() -> TestClient:
    api_module.app.dependency_overrides.clear()
    with TestClient(api_module.app, raise_server_exceptions=False) as test_client:
        yield test_client
    api_module.app.dependency_overrides.clear()


@pytest.fixture
def auth_user() -> Callable[[int], None]:
    def apply(telegram_user_id: int) -> None:
        api_module.app.dependency_overrides[api_module.require_user] = lambda: telegram_user_id

    return apply


@pytest.fixture
def db_session():
    with SessionLocal() as db:
        yield db


def make_session(
    db,
    *,
    owner_id: int = 111,
    name: str | None = None,
    phone: str = "+10000000000",
    status: SessionStatus = SessionStatus.active,
    last_send_at: datetime | None = None,
) -> TelegramSession:
    suffix = uuid.uuid4().hex[:8]
    session = TelegramSession(
        owner_telegram_id=owner_id,
        name=name or f"session-{owner_id}-{suffix}",
        phone=phone,
        telegram_user_id=owner_id + 10_000,
        username=f"user{owner_id}",
        api_id=123456,
        api_hash="0123456789abcdef0123456789abcdef",
        session_path=f"/tmp/autopost-tests/{suffix}",
        status=status,
        min_send_interval_seconds=30,
        last_send_at=last_send_at,
    )
    db.add(session)
    db.flush()
    return session


def make_chat(
    db,
    session: TelegramSession | None,
    *,
    owner_id: int | None = None,
    title: str = "Test Group",
    telegram_chat_id: int | None = None,
    chat_type: TargetChatType = TargetChatType.supergroup,
    enabled: bool = True,
) -> TargetChat:
    chat = TargetChat(
        owner_telegram_id=owner_id if owner_id is not None else session.owner_telegram_id,
        session_id=session.id if session else None,
        telegram_chat_id=telegram_chat_id or int(uuid.uuid4().int % 1_000_000_000),
        title=title,
        username=None,
        type=chat_type,
        enabled=enabled,
    )
    db.add(chat)
    db.flush()
    return chat


def make_post(
    db,
    *,
    owner_id: int = 111,
    session: TelegramSession | None = None,
    chats: list[TargetChat] | None = None,
    status: PostStatus = PostStatus.scheduled,
    schedule_kind: ScheduleKind = ScheduleKind.once,
    next_run_at: datetime | None = None,
    interval_minutes: int | None = None,
    body: str = "Post body",
) -> Post:
    post = Post(
        title=body[:60],
        body=body,
        parse_mode="html",
        status=status,
        schedule_kind=schedule_kind,
        next_run_at=next_run_at or datetime.now(UTC) + timedelta(hours=1),
        interval_minutes=interval_minutes,
        timezone="Asia/Tbilisi",
        session_strategy="fixed",
        default_session_id=session.id if session else None,
        created_by_telegram_id=owner_id,
    )
    db.add(post)
    db.flush()
    for chat in chats or []:
        db.add(PostTarget(post_id=post.id, target_chat_id=chat.id))
    db.flush()
    return post


def make_media(
    db,
    post: Post,
    *,
    media_type: str = "photo",
    file_id: str | None = None,
    source_bot_message_id: int = 10,
    order_index: int = 0,
) -> PostMedia:
    media = PostMedia(
        post_id=post.id,
        source_bot_chat_id=post.created_by_telegram_id or 111,
        source_bot_message_id=source_bot_message_id,
        media_group_id=None,
        media_type=media_type,
        file_id=file_id or f"{media_type}-file-id-{source_bot_message_id}",
        file_unique_id=f"{media_type}-unique-{source_bot_message_id}",
        order_index=order_index,
    )
    db.add(media)
    db.flush()
    return media


def make_job(
    db,
    post: Post,
    chat: TargetChat,
    *,
    session: TelegramSession | None = None,
    due_at: datetime | None = None,
    status: JobStatus = JobStatus.pending,
) -> PublishJob:
    job = PublishJob(
        post_id=post.id,
        target_chat_id=chat.id,
        session_id=session.id if session else None,
        due_at=due_at or datetime.now(UTC) - timedelta(minutes=1),
        status=status,
    )
    db.add(job)
    db.flush()
    return job
