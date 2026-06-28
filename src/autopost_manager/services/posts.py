from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from autopost_manager.config import Settings
from autopost_manager.models import ParseMode, Post, PostStatus, ScheduleKind, SessionStrategy
from autopost_manager.repositories.posts import PostRepository
from autopost_manager.repositories.publish_jobs import PublishJobRepository
from autopost_manager.repositories.target_chats import TargetChatRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.repositories.user_settings import UserSettingsRepository
from autopost_manager.schedule import WeekdaySet
from autopost_manager.schemas import DeletePostOut, PostCreate, PostMediaOut, PostOut, PostResumeUpdate, PostScheduleUpdate
from autopost_manager.services.admin import day_start, sent_since
from autopost_manager.services.telegram_cleanup import BotMessageDeleteResult, collect_source_message_refs

DeleteSourceMessages = Callable[..., Awaitable[BotMessageDeleteResult]]


def as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_schedule_weekdays(value: str | None) -> list[int]:
    return WeekdaySet.parse_storage_value(value).as_list()


def serialize_schedule_weekdays(values: list[int] | None) -> str | None:
    return WeekdaySet.from_request(values).serialize_for_storage()


def schedule_weekdays_for_storage(
    schedule_kind: ScheduleKind,
    values: list[int] | None,
) -> str | None:
    if schedule_kind != ScheduleKind.custom_weekdays:
        return None
    return serialize_schedule_weekdays(values)


def post_to_out(post: Post) -> PostOut:
    return PostOut(
        id=post.id,
        title=post.title,
        body=post.body,
        parse_mode=ParseMode(post.parse_mode) if post.parse_mode else None,
        status=post.status,
        schedule_kind=post.schedule_kind,
        next_run_at=post.next_run_at,
        interval_minutes=post.interval_minutes,
        schedule_weekdays=parse_schedule_weekdays(post.schedule_weekdays),
        timezone=post.timezone,
        session_strategy=SessionStrategy(post.session_strategy),
        default_session_id=post.default_session_id,
        target_chat_ids=[target.target_chat_id for target in post.targets],
        media=[
            PostMediaOut.model_validate(media)
            for media in sorted(post.media_items, key=lambda item: item.order_index)
        ],
    )


@dataclass(kw_only=True, frozen=True, slots=True)
class PostService:
    db: Session
    settings: Settings

    def list_posts(self, *, telegram_user_id: int) -> list[PostOut]:
        if not self._active_account(telegram_user_id):
            return []
        return [post_to_out(post) for post in PostRepository(self.db).list_for_owner(telegram_user_id)]

    def create_post(self, *, payload: PostCreate, telegram_user_id: int) -> PostOut:
        self._require_autopost_enabled(telegram_user_id)
        if payload.status == PostStatus.scheduled:
            self._enforce_active_post_limit(telegram_user_id)
            self._validate_post_schedule(
                schedule_kind=payload.schedule_kind,
                next_run_at=payload.next_run_at,
                interval_minutes=payload.interval_minutes,
                schedule_weekdays=payload.schedule_weekdays,
                spam_risk_acknowledged=payload.spam_risk_acknowledged,
                default_session_id=payload.default_session_id,
                target_chat_ids=payload.target_chat_ids,
            )

        self._validate_owned_session_and_targets(
            telegram_user_id=telegram_user_id,
            session_id=payload.default_session_id,
            target_chat_ids=payload.target_chat_ids,
        )

        post_data = payload.model_dump(
            exclude={"target_chat_ids", "spam_risk_acknowledged", "schedule_weekdays"}
        )
        post_data["schedule_weekdays"] = schedule_weekdays_for_storage(
            payload.schedule_kind,
            payload.schedule_weekdays,
        )
        post = Post(**post_data, created_by_telegram_id=telegram_user_id)
        self.db.add(post)
        self.db.flush()
        PostRepository(self.db).replace_targets(post, payload.target_chat_ids)
        self.db.commit()
        self.db.refresh(post)
        return post_to_out(post)

    def schedule_post(self, *, post_id: UUID, payload: PostScheduleUpdate, telegram_user_id: int) -> PostOut:
        post = self._owned_post_or_404(post_id, telegram_user_id)
        self._require_active_account(telegram_user_id)
        self._require_autopost_enabled(telegram_user_id)
        self._enforce_active_post_limit(telegram_user_id, current_post=post)
        if len(post.media_items) > self.settings.max_media_items_per_post:
            raise HTTPException(status_code=422, detail="Слишком много медиа в одном посте")

        self._validate_post_schedule(
            schedule_kind=payload.schedule_kind,
            next_run_at=payload.next_run_at,
            interval_minutes=payload.interval_minutes,
            schedule_weekdays=payload.schedule_weekdays,
            spam_risk_acknowledged=payload.spam_risk_acknowledged,
            default_session_id=payload.default_session_id,
            target_chat_ids=payload.target_chat_ids,
        )
        self._validate_owned_session_and_targets(
            telegram_user_id=telegram_user_id,
            session_id=payload.default_session_id,
            target_chat_ids=payload.target_chat_ids,
        )

        post.status = PostStatus.scheduled
        post.schedule_kind = payload.schedule_kind
        post.next_run_at = payload.next_run_at
        post.interval_minutes = payload.interval_minutes
        post.schedule_weekdays = schedule_weekdays_for_storage(
            payload.schedule_kind,
            payload.schedule_weekdays,
        )
        post.timezone = payload.timezone
        post.default_session_id = payload.default_session_id
        PublishJobRepository(self.db).cancel_pending_for_post(post.id)
        PostRepository(self.db).replace_targets(post, payload.target_chat_ids)
        self.db.commit()
        self.db.refresh(post)
        return post_to_out(post)

    def pause_post(self, *, post_id: UUID, telegram_user_id: int) -> PostOut:
        post = self._owned_post_or_404(post_id, telegram_user_id)
        self._require_active_account(telegram_user_id)
        self._require_autopost_enabled(telegram_user_id)
        if post.status not in {PostStatus.scheduled, PostStatus.paused}:
            raise HTTPException(status_code=409, detail="Можно поставить на паузу только пост из очереди")

        post.status = PostStatus.paused
        PublishJobRepository(self.db).cancel_pending_for_post(post.id)
        self.db.commit()
        self.db.refresh(post)
        return post_to_out(post)

    def resume_post(self, *, post_id: UUID, payload: PostResumeUpdate, telegram_user_id: int) -> PostOut:
        post = self._owned_post_or_404(post_id, telegram_user_id)
        self._require_active_account(telegram_user_id)
        self._require_autopost_enabled(telegram_user_id)
        if post.status != PostStatus.paused:
            raise HTTPException(status_code=409, detail="Пост не на паузе")

        next_run_at = payload.next_run_at or post.next_run_at
        if next_run_at is None or as_aware(next_run_at) <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Выберите новую будущую дату отправки")

        post.next_run_at = next_run_at
        post.status = PostStatus.scheduled
        self.db.commit()
        self.db.refresh(post)
        return post_to_out(post)

    def enqueue_now(self, *, post_id: UUID, telegram_user_id: int) -> dict[str, object]:
        post = self._owned_post_or_404(post_id, telegram_user_id)
        self._require_active_account(telegram_user_id)
        self._require_autopost_enabled(telegram_user_id)
        if len({target.target_chat_id for target in post.targets}) > self.settings.max_targets_per_post:
            raise HTTPException(
                status_code=422,
                detail=f"Можно выбрать не больше {self.settings.max_targets_per_post} групп на один пост",
            )
        self._enforce_daily_job_creation_limit(telegram_user_id, len(post.targets))

        count = 0
        publish_jobs = PublishJobRepository(self.db)
        for target in post.targets:
            if publish_jobs.active_for_post_target(post_id=post.id, target_chat_id=target.target_chat_id):
                continue
            publish_jobs.add_pending(
                post_id=post.id,
                target_chat_id=target.target_chat_id,
                session_id=post.default_session_id,
                due_at=post.next_run_at or post.created_at,
            )
            count += 1
        self.db.commit()
        return {"ok": True, "jobs_created": count}

    async def delete_post(
        self,
        *,
        post_id: UUID,
        telegram_user_id: int,
        delete_source_messages: DeleteSourceMessages,
        ack_text: str,
    ) -> DeletePostOut:
        post = self._owned_post_or_404(post_id, telegram_user_id)
        self._require_active_account(telegram_user_id)
        self._require_autopost_enabled(telegram_user_id)

        message_refs = collect_source_message_refs(post)
        match_texts = {post.body}
        created_at = post.created_at
        media_count = len(post.media_items)
        deleted_jobs = PublishJobRepository(self.db).delete_for_post(post.id)
        PostRepository(self.db).delete(post)
        self.db.commit()
        telegram_delete = await delete_source_messages(
            telegram_user_id=telegram_user_id,
            refs=message_refs,
            db=self.db,
            match_texts=match_texts,
            ack_text=ack_text,
            created_at=created_at,
            media_count=media_count,
        )

        return DeletePostOut(
            ok=True,
            deleted_jobs=deleted_jobs,
            source_messages_found=len(message_refs),
            telegram_delete_attempted=telegram_delete.attempted,
            deleted_bot_messages=telegram_delete.deleted,
            telegram_delete_errors=telegram_delete.errors,
        )

    def _owned_post_or_404(self, post_id: UUID, telegram_user_id: int) -> Post:
        post = PostRepository(self.db).fetch_owned(post_id, telegram_user_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        return post

    def _active_account(self, telegram_user_id: int):
        return TelegramSessionRepository(self.db).active_for_owner(telegram_user_id)

    def _require_active_account(self, telegram_user_id: int) -> None:
        if not self._active_account(telegram_user_id):
            raise HTTPException(status_code=409, detail="Сначала подключите Telegram-аккаунт")

    def _require_autopost_enabled(self, telegram_user_id: int) -> None:
        settings = UserSettingsRepository(self.db).fetch_by_user_id(telegram_user_id)
        if settings and settings.banned:
            raise HTTPException(status_code=403, detail="Пользователь заблокирован администратором")
        if settings and settings.autopost_paused:
            raise HTTPException(status_code=409, detail="Автопостинг на паузе")
        if (
            settings
            and settings.daily_send_limit is not None
            and sent_since(self.db, telegram_user_id=telegram_user_id, since=day_start())
            >= settings.daily_send_limit
        ):
            raise HTTPException(status_code=429, detail="Достигнут дневной лимит отправки постов")

    def _enforce_active_post_limit(self, telegram_user_id: int, *, current_post: Post | None = None) -> None:
        count = PostRepository(self.db).count_active_scheduled_for_owner(telegram_user_id)
        if current_post and current_post.status == PostStatus.scheduled:
            count -= 1
        if count >= self.settings.max_active_posts_per_user:
            raise HTTPException(status_code=429, detail="Достигнут лимит активных запланированных постов")

    def _enforce_daily_job_creation_limit(self, telegram_user_id: int, jobs_to_create: int) -> None:
        today_jobs = PublishJobRepository(self.db).count_created_since_for_owner(
            owner_telegram_id=telegram_user_id,
            since=day_start(),
        )
        if today_jobs + jobs_to_create > self.settings.max_jobs_per_user_per_day:
            raise HTTPException(status_code=429, detail="Достигнут дневной лимит постановки задач в очередь")

    def _validate_post_schedule(
        self,
        *,
        schedule_kind: ScheduleKind,
        next_run_at: datetime | None,
        interval_minutes: int | None,
        schedule_weekdays: list[int] | None,
        spam_risk_acknowledged: bool,
        default_session_id: UUID | None,
        target_chat_ids: list[UUID],
    ) -> None:
        if next_run_at is None:
            raise HTTPException(status_code=422, detail="Выберите дату отправки")
        if as_aware(next_run_at) <= datetime.now(UTC):
            raise HTTPException(status_code=422, detail="Выберите будущую дату отправки")

        if schedule_kind == ScheduleKind.interval:
            if interval_minutes is None:
                raise HTTPException(status_code=422, detail="Укажите интервал повтора")
            if interval_minutes < 20:
                raise HTTPException(status_code=422, detail="Минимальный интервал повтора — 20 минут")
            if interval_minutes <= 30 and not spam_risk_acknowledged:
                raise HTTPException(
                    status_code=422,
                    detail="Подтвердите риск: за частую отправку сообщений Telegram может ограничить аккаунт",
                )
        elif schedule_kind == ScheduleKind.custom_weekdays:
            days = serialize_schedule_weekdays(schedule_weekdays)
            if not days:
                raise HTTPException(status_code=422, detail="Выберите хотя бы один день недели")

        if not default_session_id:
            raise HTTPException(status_code=422, detail="Сначала подключите Telegram-аккаунт")
        if not target_chat_ids:
            raise HTTPException(status_code=422, detail="Выберите хотя бы одну группу")
        if len(set(target_chat_ids)) > self.settings.max_targets_per_post:
            raise HTTPException(
                status_code=422,
                detail=f"Можно выбрать не больше {self.settings.max_targets_per_post} групп на один пост",
            )

    def _validate_owned_session_and_targets(
        self,
        *,
        telegram_user_id: int,
        session_id: UUID | None,
        target_chat_ids: list[UUID],
    ) -> None:
        if session_id:
            session = TelegramSessionRepository(self.db).fetch_owned_active(session_id, telegram_user_id)
            if not session:
                raise HTTPException(status_code=404, detail="Telegram account not found")

        for target_chat_id in target_chat_ids:
            target = TargetChatRepository(self.db).fetch_owned_enabled(target_chat_id, telegram_user_id)
            if not target:
                raise HTTPException(status_code=404, detail="Group not found")
