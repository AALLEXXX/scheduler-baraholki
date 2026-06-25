"""bootstrap existing autopost schema

Revision ID: 20260626_0001
Revises:
Create Date: 2026-06-26 02:30:00.000000
"""

from __future__ import annotations

from alembic import op

from autopost_manager import models  # noqa: F401
from autopost_manager.db import Base


revision = "20260626_0001"
down_revision = None
branch_labels = None
depends_on = None


POSTGRES_RUNTIME_STATEMENTS = [
    "ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'credentials_needed'",
    "ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'code_needed'",
    "ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'password_needed'",
    "ALTER TYPE schedulekind ADD VALUE IF NOT EXISTS 'weekdays'",
    "ALTER TYPE schedulekind ADD VALUE IF NOT EXISTS 'weekends'",
    "ALTER TYPE schedulekind ADD VALUE IF NOT EXISTS 'every_other_day'",
    "ALTER TYPE schedulekind ADD VALUE IF NOT EXISTS 'custom_weekdays'",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS banned BOOLEAN DEFAULT false",
    "ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS daily_send_limit INTEGER",
    "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS owner_telegram_id BIGINT",
    "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS api_id INTEGER",
    "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS api_hash VARCHAR(160)",
    "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS phone_code_hash VARCHAR(300)",
    "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS session_string TEXT",
    "ALTER TABLE telegram_sessions ADD COLUMN IF NOT EXISTS last_code_requested_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE target_chats ADD COLUMN IF NOT EXISTS owner_telegram_id BIGINT",
    "ALTER TABLE target_chats ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT true",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS source_bot_chat_id BIGINT",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS source_bot_message_id BIGINT",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS source_media_group_id VARCHAR(120)",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS ack_bot_chat_id BIGINT",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS ack_bot_message_id BIGINT",
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS schedule_weekdays VARCHAR(40)",
    "CREATE INDEX IF NOT EXISTS ix_telegram_sessions_owner_telegram_id ON telegram_sessions (owner_telegram_id)",
    "CREATE INDEX IF NOT EXISTS ix_target_chats_owner_telegram_id ON target_chats (owner_telegram_id)",
    "CREATE INDEX IF NOT EXISTS ix_posts_source_media_group_id ON posts (source_media_group_id)",
]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        for statement in POSTGRES_RUNTIME_STATEMENTS:
            op.execute(statement)


def downgrade() -> None:
    pass
