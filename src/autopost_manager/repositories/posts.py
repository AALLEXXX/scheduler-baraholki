from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from autopost_manager.models import Post, PostMedia, PostStatus, PostTarget, UserSettings


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

    def list_due_scheduled_unblocked(self, now) -> list[Post]:
        blocked_owner_exists = exists().where(
            UserSettings.telegram_user_id == Post.created_by_telegram_id,
            (UserSettings.autopost_paused.is_(True)) | (UserSettings.banned.is_(True)),
        )
        return (
            self.db.scalars(
                select(Post)
                .where(Post.status == PostStatus.scheduled)
                .where(Post.next_run_at.is_not(None))
                .where(Post.next_run_at <= now)
                .where(~blocked_owner_exists)
                .with_for_update(skip_locked=True, of=Post)
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

    def find_draft_album(self, owner_telegram_id: int, media_group_id: str) -> Post | None:
        return self.db.scalars(
            select(Post)
            .join(PostMedia)
            .where(Post.created_by_telegram_id == owner_telegram_id)
            .where(Post.status == PostStatus.draft)
            .where(PostMedia.media_group_id == media_group_id)
            .order_by(Post.created_at.desc())
        ).first()

    def count_drafts_for_owner(self, owner_telegram_id: int) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(Post)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .where(Post.status == PostStatus.draft)
            )
            or 0
        )

    def count_media(self, post_id: UUID) -> int:
        return int(self.db.scalar(select(func.count(PostMedia.id)).where(PostMedia.post_id == post_id)) or 0)

    def fetch_media_by_source(
        self,
        *,
        post_id: UUID,
        source_bot_chat_id: int,
        source_bot_message_id: int,
    ) -> PostMedia | None:
        return self.db.scalars(
            select(PostMedia)
            .where(PostMedia.post_id == post_id)
            .where(PostMedia.source_bot_chat_id == source_bot_chat_id)
            .where(PostMedia.source_bot_message_id == source_bot_message_id)
        ).first()

    def pause_scheduled_for_owner(self, owner_telegram_id: int) -> int:
        posts = list(
            self.db.scalars(
                select(Post)
                .where(Post.created_by_telegram_id == owner_telegram_id)
                .where(Post.status == PostStatus.scheduled)
            )
        )
        for post in posts:
            post.status = PostStatus.paused
        return len(posts)

    def replace_targets(self, post: Post, target_chat_ids: list[UUID]) -> None:
        post.targets.clear()
        self.db.flush()
        for target_chat_id in target_chat_ids:
            self.db.add(PostTarget(post_id=post.id, target_chat_id=target_chat_id))

    def delete(self, post: Post) -> None:
        self.db.delete(post)
