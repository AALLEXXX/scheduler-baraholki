from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aiogram import Bot
from sqlalchemy.orm import Session

from autopost_manager.models import Post
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository

SendAlert = Callable[..., Awaitable[None]]
DeleteMessages = Callable[..., Awaitable[int]]
DeleteBotMessages = Callable[[set[tuple[int, int]]], Awaitable["BotMessageDeleteResult"]]
BotFactory = Callable[[str], Any]


@dataclass
class BotMessageDeleteResult:
    attempted: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)


def collect_source_message_refs(post: Post) -> set[tuple[int, int]]:
    refs: set[tuple[int, int]] = set()
    if post.source_bot_chat_id and post.source_bot_message_id:
        refs.add((post.source_bot_chat_id, post.source_bot_message_id))
    if post.ack_bot_chat_id and post.ack_bot_message_id:
        refs.add((post.ack_bot_chat_id, post.ack_bot_message_id))
    for media in post.media_items:
        refs.add((media.source_bot_chat_id, media.source_bot_message_id))
    return refs


@dataclass(slots=True)
class TelegramCleanupService:
    db: Session | None
    bot_token: str
    bot_username: str
    send_alert: SendAlert
    delete_messages_from_session: DeleteMessages
    bot_factory: BotFactory = Bot

    async def delete_bot_messages(self, refs: set[tuple[int, int]]) -> BotMessageDeleteResult:
        result = BotMessageDeleteResult()
        if not refs:
            return result

        bot = self.bot_factory(self.bot_token)
        try:
            for chat_id, message_id in refs:
                result.attempted += 1
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=message_id)
                except Exception as exc:
                    result.errors.append(f"{chat_id}/{message_id}: {exc}")
                    await self.send_alert(
                        title="Bot message delete error",
                        status="error",
                        fields={
                            "action": "delete_bot_message",
                            "bot_chat_id": chat_id,
                            "bot_message_id": message_id,
                            "error_type": type(exc).__name__,
                            "error": exc,
                        },
                    )
                    continue
                result.deleted += 1
        finally:
            await bot.session.close()
        return result

    async def delete_source_messages(
        self,
        *,
        telegram_user_id: int,
        refs: set[tuple[int, int]],
        delete_bot_messages: DeleteBotMessages,
        match_texts: set[str] | None = None,
        ack_text: str | None = None,
        created_at: datetime | None = None,
        media_count: int = 0,
    ) -> BotMessageDeleteResult:
        if not refs and not match_texts and not ack_text and not media_count:
            return BotMessageDeleteResult()
        if self.db is None:
            return await delete_bot_messages(refs)

        message_ids = sorted({message_id for _chat_id, message_id in refs})
        session = TelegramSessionRepository(self.db).active_for_owner(telegram_user_id)
        if not session:
            return await delete_bot_messages(refs)

        result = BotMessageDeleteResult(attempted=len(message_ids))
        try:
            bot_peer = f"@{self.bot_username.lstrip('@')}"
            result.deleted = await self.delete_messages_from_session(
                session=session,
                peer=bot_peer,
                message_ids=message_ids,
                match_texts=match_texts,
                ack_text=ack_text,
                created_at=created_at,
                media_count=media_count,
            )
            result.attempted = max(result.attempted, result.deleted)
        except Exception as exc:
            result.errors.append(f"user session: {exc}")
            await self.send_alert(
                title="Source message delete error",
                status="error",
                fields={
                    "action": "delete_source_messages",
                    "owner_telegram_id": telegram_user_id,
                    "source_message_ids": ",".join(str(message_id) for message_id in message_ids),
                    "error_type": type(exc).__name__,
                    "error": exc,
                },
            )

        if result.deleted == 0:
            fallback = await delete_bot_messages(refs)
            result.attempted += fallback.attempted
            result.deleted += fallback.deleted
            result.errors.extend(fallback.errors)

        return result
