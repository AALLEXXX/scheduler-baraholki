from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from autopost_manager.models import Post, PostStatus, PostTarget


class PostRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def fetch_by_id(self, post_id: UUID) -> Post | None:
        return self.db.get(Post, post_id)

    def fetch_owned(self, post_id: UUID, owner_telegram_id: int) -> Post | None:
        post = self.fetch_by_id(post_id)
        if not post or post.created_by_telegram_id != owner_telegram_id:
            return None
        return post

    def list_for_owner(self, owner_telegram_id: int) -> list[Post]:
        return (
            self.db.scalars(
                select(Post)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .order_by(Post.created_at.desc())
            )
            .unique()
            .all()
        )

    def count_active_scheduled_for_owner(self, owner_telegram_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Post)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .where(Post.status == PostStatus.scheduled)
            )
            or 0
        )

    def replace_targets(self, post: Post, target_chat_ids: list[UUID]) -> None:
        post.targets.clear()
        self.db.flush()
        for target_chat_id in target_chat_ids:
            self.db.add(PostTarget(post_id=post.id, target_chat_id=target_chat_id))

    def delete(self, post: Post) -> None:
        self.db.delete(post)
