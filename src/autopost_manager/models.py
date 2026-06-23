from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autopost_manager.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class SessionStatus(str, enum.Enum):
    credentials_needed = "credentials_needed"
    code_needed = "code_needed"
    password_needed = "password_needed"
    needs_login = "needs_login"
    active = "active"
    paused = "paused"
    limited = "limited"
    revoked = "revoked"


class PostStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    paused = "paused"
    archived = "archived"


class ScheduleKind(str, enum.Enum):
    once = "once"
    interval = "interval"
    daily = "daily"
    weekly = "weekly"
    weekdays = "weekdays"
    weekends = "weekends"
    every_other_day = "every_other_day"
    custom_weekdays = "custom_weekdays"


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class TargetChatType(str, enum.Enum):
    group = "group"
    supergroup = "supergroup"
    channel = "channel"


class TelegramSession(Base):
    __tablename__ = "telegram_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    username: Mapped[str | None] = mapped_column(String(120))
    api_id: Mapped[int | None] = mapped_column(Integer)
    api_hash: Mapped[str | None] = mapped_column(String(160))
    phone_code_hash: Mapped[str | None] = mapped_column(String(300))
    session_string: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), default=SessionStatus.needs_login
    )
    session_path: Mapped[str] = mapped_column(String(500))
    min_send_interval_seconds: Mapped[int] = mapped_column(Integer, default=30)
    last_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_code_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    chats: Mapped[list["TargetChat"]] = relationship(back_populates="session")


class TargetChat(Base):
    __tablename__ = "target_chats"
    __table_args__ = (UniqueConstraint("session_id", "telegram_chat_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_telegram_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("telegram_sessions.id"))
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(240))
    username: Mapped[str | None] = mapped_column(String(120))
    type: Mapped[TargetChatType] = mapped_column(Enum(TargetChatType))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[TelegramSession | None] = relationship(back_populates="chats")
    posts: Mapped[list["PostTarget"]] = relationship(back_populates="target_chat")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    parse_mode: Mapped[str | None] = mapped_column(String(20), default="html")
    status: Mapped[PostStatus] = mapped_column(Enum(PostStatus), default=PostStatus.draft)
    schedule_kind: Mapped[ScheduleKind] = mapped_column(
        Enum(ScheduleKind), default=ScheduleKind.once
    )
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    interval_minutes: Mapped[int | None] = mapped_column(Integer)
    schedule_weekdays: Mapped[str | None] = mapped_column(String(40))
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Tbilisi")
    session_strategy: Mapped[str] = mapped_column(String(40), default="fixed")
    default_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("telegram_sessions.id"))
    created_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    source_bot_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    source_bot_message_id: Mapped[int | None] = mapped_column(BigInteger)
    source_media_group_id: Mapped[str | None] = mapped_column(String(120), index=True)
    ack_bot_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    ack_bot_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    targets: Mapped[list["PostTarget"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )
    media_items: Mapped[list["PostMedia"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="PostMedia.order_index",
    )


class PostTarget(Base):
    __tablename__ = "post_targets"
    __table_args__ = (UniqueConstraint("post_id", "target_chat_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"))
    target_chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("target_chats.id"))

    post: Mapped[Post] = relationship(back_populates="targets")
    target_chat: Mapped[TargetChat] = relationship(back_populates="posts")


class PostMedia(Base):
    __tablename__ = "post_media"
    __table_args__ = (UniqueConstraint("post_id", "source_bot_chat_id", "source_bot_message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"), index=True)
    source_bot_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_bot_message_id: Mapped[int] = mapped_column(BigInteger)
    media_group_id: Mapped[str | None] = mapped_column(String(120), index=True)
    media_type: Mapped[str] = mapped_column(String(40))
    file_id: Mapped[str] = mapped_column(Text)
    file_unique_id: Mapped[str | None] = mapped_column(String(200))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped[Post] = relationship(back_populates="media_items")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("posts.id"))
    target_chat_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("target_chats.id"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("telegram_sessions.id"))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.pending)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    post: Mapped[Post] = relationship()
    target_chat: Mapped[TargetChat] = relationship()
    session: Mapped[TelegramSession | None] = relationship()
