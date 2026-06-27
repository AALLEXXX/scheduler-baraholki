from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260626_0004_publish_job_reliability_fields"
down_revision = "20260626_0003_publish_job_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        statements = [
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS error_code VARCHAR(80)",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS error_kind VARCHAR(80)",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS worker_id VARCHAR(120)",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP WITH TIME ZONE",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_locked_at ON publish_jobs (locked_at)",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_worker_id ON publish_jobs (worker_id)",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_completed_at ON publish_jobs (completed_at)",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_cancelled_at ON publish_jobs (cancelled_at)",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_status_due_at ON publish_jobs (status, due_at)",
            "CREATE INDEX IF NOT EXISTS ix_posts_owner_status_next_run ON posts (created_by_telegram_id, status, next_run_at)",
        ]
        for statement in statements:
            op.execute(statement)
        return

    op.add_column("publish_jobs", sa.Column("max_attempts", sa.Integer(), nullable=True, server_default="3"))
    op.add_column("publish_jobs", sa.Column("error_code", sa.String(length=80), nullable=True))
    op.add_column("publish_jobs", sa.Column("error_kind", sa.String(length=80), nullable=True))
    op.add_column("publish_jobs", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_jobs", sa.Column("worker_id", sa.String(length=120), nullable=True))
    op.add_column("publish_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_jobs", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_publish_jobs_locked_at", "publish_jobs", ["locked_at"])
    op.create_index("ix_publish_jobs_worker_id", "publish_jobs", ["worker_id"])
    op.create_index("ix_publish_jobs_completed_at", "publish_jobs", ["completed_at"])
    op.create_index("ix_publish_jobs_cancelled_at", "publish_jobs", ["cancelled_at"])
    op.create_index("ix_publish_jobs_status_due_at", "publish_jobs", ["status", "due_at"])
    op.create_index("ix_posts_owner_status_next_run", "posts", ["created_by_telegram_id", "status", "next_run_at"])


def downgrade() -> None:
    op.drop_index("ix_posts_owner_status_next_run", table_name="posts")
    op.drop_index("ix_publish_jobs_status_due_at", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_cancelled_at", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_completed_at", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_worker_id", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_locked_at", table_name="publish_jobs")
    op.drop_column("publish_jobs", "cancelled_at")
    op.drop_column("publish_jobs", "completed_at")
    op.drop_column("publish_jobs", "worker_id")
    op.drop_column("publish_jobs", "locked_at")
    op.drop_column("publish_jobs", "error_kind")
    op.drop_column("publish_jobs", "error_code")
    op.drop_column("publish_jobs", "max_attempts")
