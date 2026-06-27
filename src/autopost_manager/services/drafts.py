from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from autopost_manager.config import Settings
from autopost_manager.models import Post, PostMedia, PostStatus, ScheduleKind
from autopost_manager.repositories.posts import PostRepository


class DraftLimitError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DraftMediaInput:
    media_type: str
    file_id: str
    file_unique_id: str | None


@dataclass(frozen=True, slots=True)
class DraftInput:
    owner_telegram_id: int
    title: str
    html_body: str
    source_bot_chat_id: int
    source_bot_message_id: int
    source_media_group_id: str | None
    media: DraftMediaInput | None


@dataclass(slots=True)
class DraftService:
    db: Session
    settings: Settings

    def create_or_update_draft(self, draft_input: DraftInput) -> tuple[Post, bool]:
        posts = PostRepository(self.db)
        post = (
            posts.find_draft_album(
                draft_input.owner_telegram_id,
                draft_input.source_media_group_id,
            )
            if draft_input.source_media_group_id
            else None
        )
        created = post is None

        if not post:
            if posts.count_drafts_for_owner(draft_input.owner_telegram_id) >= self.settings.max_drafts_per_user:
                raise DraftLimitError("Достигнут лимит черновиков. Удалите старые черновики.")
            post = Post(
                title=draft_input.title,
                body=draft_input.html_body,
                parse_mode="html",
                status=PostStatus.draft,
                schedule_kind=ScheduleKind.once,
                timezone="Asia/Tbilisi",
                session_strategy="fixed",
                created_by_telegram_id=draft_input.owner_telegram_id,
                source_bot_chat_id=draft_input.source_bot_chat_id,
                source_bot_message_id=draft_input.source_bot_message_id,
                source_media_group_id=draft_input.source_media_group_id,
            )
            self.db.add(post)
            self.db.flush()
        elif draft_input.html_body and not post.body:
            post.body = draft_input.html_body
            post.title = draft_input.title

        if draft_input.media:
            if posts.count_media(post.id) >= self.settings.max_media_items_per_post:
                raise DraftLimitError("Слишком много медиа в одном черновике.")
            existing_media = posts.fetch_media_by_source(
                post_id=post.id,
                source_bot_chat_id=draft_input.source_bot_chat_id,
                source_bot_message_id=draft_input.source_bot_message_id,
            )
            if not existing_media:
                self.db.add(
                    PostMedia(
                        post_id=post.id,
                        source_bot_chat_id=draft_input.source_bot_chat_id,
                        source_bot_message_id=draft_input.source_bot_message_id,
                        media_group_id=draft_input.source_media_group_id,
                        media_type=draft_input.media.media_type,
                        file_id=draft_input.media.file_id,
                        file_unique_id=draft_input.media.file_unique_id,
                        order_index=posts.count_media(post.id),
                    )
                )

        self.db.commit()
        self.db.refresh(post)
        return post, created

    def save_ack_message(self, post_id: UUID, *, ack_chat_id: int, ack_message_id: int) -> None:
        post = PostRepository(self.db).fetch_by_id(post_id)
        if not post:
            return
        post.ack_bot_chat_id = ack_chat_id
        post.ack_bot_message_id = ack_message_id
        self.db.commit()
