from __future__ import annotations

from alembic import op

revision = "20260628_0005_multi_user_owner_constraints"
down_revision = "20260626_0004_publish_job_reliability_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        statements = [
            """
            UPDATE telegram_sessions
            SET owner_telegram_id = telegram_user_id
            WHERE owner_telegram_id IS NULL
              AND telegram_user_id IS NOT NULL
            """,
            """
            UPDATE target_chats
            SET owner_telegram_id = telegram_sessions.owner_telegram_id
            FROM telegram_sessions
            WHERE target_chats.session_id = telegram_sessions.id
              AND target_chats.owner_telegram_id IS NULL
              AND telegram_sessions.owner_telegram_id IS NOT NULL
            """,
            """
            DELETE FROM publish_jobs
            USING posts
            WHERE publish_jobs.post_id = posts.id
              AND posts.created_by_telegram_id IS NULL
            """,
            """
            DELETE FROM post_media
            USING posts
            WHERE post_media.post_id = posts.id
              AND posts.created_by_telegram_id IS NULL
            """,
            """
            DELETE FROM post_targets
            USING posts
            WHERE post_targets.post_id = posts.id
              AND posts.created_by_telegram_id IS NULL
            """,
            "DELETE FROM posts WHERE created_by_telegram_id IS NULL",
            """
            DELETE FROM publish_jobs
            USING target_chats
            WHERE publish_jobs.target_chat_id = target_chats.id
              AND (target_chats.owner_telegram_id IS NULL OR target_chats.session_id IS NULL)
            """,
            """
            DELETE FROM post_targets
            USING target_chats
            WHERE post_targets.target_chat_id = target_chats.id
              AND (target_chats.owner_telegram_id IS NULL OR target_chats.session_id IS NULL)
            """,
            "DELETE FROM target_chats WHERE owner_telegram_id IS NULL OR session_id IS NULL",
            """
            UPDATE publish_jobs
            SET session_id = NULL
            WHERE session_id IN (
                SELECT id FROM telegram_sessions WHERE owner_telegram_id IS NULL
            )
            """,
            "DELETE FROM telegram_sessions WHERE owner_telegram_id IS NULL",
            "ALTER TABLE telegram_sessions ALTER COLUMN owner_telegram_id SET NOT NULL",
            "ALTER TABLE target_chats ALTER COLUMN owner_telegram_id SET NOT NULL",
            "ALTER TABLE target_chats ALTER COLUMN session_id SET NOT NULL",
            "ALTER TABLE posts ALTER COLUMN created_by_telegram_id SET NOT NULL",
            "ALTER TABLE telegram_sessions DROP CONSTRAINT IF EXISTS telegram_sessions_name_key",
            "DROP INDEX IF EXISTS ix_telegram_sessions_owner_name",
            "DROP INDEX IF EXISTS ix_telegram_sessions_owner_phone",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_sessions_owner_name ON telegram_sessions (owner_telegram_id, name)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_sessions_owner_phone ON telegram_sessions (owner_telegram_id, phone)",
        ]
        for statement in statements:
            op.execute(statement)
        return

    return


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        statements = [
            "DROP INDEX IF EXISTS uq_telegram_sessions_owner_phone",
            "DROP INDEX IF EXISTS uq_telegram_sessions_owner_name",
            "ALTER TABLE posts ALTER COLUMN created_by_telegram_id DROP NOT NULL",
            "ALTER TABLE target_chats ALTER COLUMN session_id DROP NOT NULL",
            "ALTER TABLE target_chats ALTER COLUMN owner_telegram_id DROP NOT NULL",
            "ALTER TABLE telegram_sessions ALTER COLUMN owner_telegram_id DROP NOT NULL",
            "ALTER TABLE telegram_sessions ADD CONSTRAINT telegram_sessions_name_key UNIQUE (name)",
        ]
        for statement in statements:
            op.execute(statement)
        return

    return
