from __future__ import annotations

from alembic import op

revision = "20260626_0003_publish_job_idempotency"
down_revision = "20260626_0002_security_limits"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_publish_jobs_post_target_due_at"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DELETE FROM publish_jobs duplicate
            USING publish_jobs original
            WHERE duplicate.id > original.id
              AND duplicate.post_id = original.post_id
              AND duplicate.target_chat_id = original.target_chat_id
              AND duplicate.due_at = original.due_at
            """
        )
    op.create_index(
        INDEX_NAME,
        "publish_jobs",
        ["post_id", "target_chat_id", "due_at"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="publish_jobs")
