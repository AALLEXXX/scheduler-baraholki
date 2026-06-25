from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260626_0002_security_limits"
down_revision = "20260626_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        statements = [
            "CREATE TABLE IF NOT EXISTS rate_limit_events (id UUID PRIMARY KEY, scope VARCHAR(80) NOT NULL, key VARCHAR(240) NOT NULL, created_at TIMESTAMP WITH TIME ZONE NOT NULL)",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE",
            "ALTER TABLE publish_jobs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP WITH TIME ZONE",
            "CREATE INDEX IF NOT EXISTS ix_rate_limit_events_scope ON rate_limit_events (scope)",
            "CREATE INDEX IF NOT EXISTS ix_rate_limit_events_key ON rate_limit_events (key)",
            "CREATE INDEX IF NOT EXISTS ix_rate_limit_events_created_at ON rate_limit_events (created_at)",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_locked_until ON publish_jobs (locked_until)",
            "CREATE INDEX IF NOT EXISTS ix_publish_jobs_next_attempt_at ON publish_jobs (next_attempt_at)",
        ]
        for statement in statements:
            op.execute(statement)
        return

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("key", sa.String(length=240), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_events_scope", "rate_limit_events", ["scope"])
    op.create_index("ix_rate_limit_events_key", "rate_limit_events", ["key"])
    op.create_index("ix_rate_limit_events_created_at", "rate_limit_events", ["created_at"])
    op.add_column("publish_jobs", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publish_jobs", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_publish_jobs_locked_until", "publish_jobs", ["locked_until"])
    op.create_index("ix_publish_jobs_next_attempt_at", "publish_jobs", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_publish_jobs_next_attempt_at", table_name="publish_jobs")
    op.drop_index("ix_publish_jobs_locked_until", table_name="publish_jobs")
    op.drop_column("publish_jobs", "next_attempt_at")
    op.drop_column("publish_jobs", "locked_until")
    op.drop_index("ix_rate_limit_events_created_at", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_key", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_scope", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")
