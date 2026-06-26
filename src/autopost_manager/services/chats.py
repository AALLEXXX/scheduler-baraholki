from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from autopost_manager.models import TargetChat, TargetChatType
from autopost_manager.repositories.target_chats import TargetChatRepository
from autopost_manager.repositories.telegram_sessions import TelegramSessionRepository
from autopost_manager.schemas import DialogFolderOut

logger = logging.getLogger(__name__)

DialogLoader = Callable[..., Awaitable[list[dict[str, object]]]]
FolderLoader = Callable[..., Awaitable[list[dict[str, object]]]]
SendAlert = Callable[..., Awaitable[None]]


@dataclass(slots=True)
class ChatService:
    db: Session
    list_dialogs: DialogLoader
    list_folders_from_session: FolderLoader
    send_alert: SendAlert

    async def sync_session_chats(self, *, session_id: UUID, telegram_user_id: int) -> dict[str, int]:
        sender_session = TelegramSessionRepository(self.db).fetch_owned(session_id, telegram_user_id)
        if not sender_session:
            raise HTTPException(status_code=404, detail="Telegram account not found")

        try:
            dialogs = await self.list_dialogs(sender_session)
        except RuntimeError as exc:
            logger.warning("Telegram dialog sync failed: session_id=%s error=%s", sender_session.id, exc)
            await self.send_alert(
                title="Telegram dialog sync error",
                status="409",
                fields={
                    "action": "sync_chats",
                    "owner_telegram_id": telegram_user_id,
                    "session_id": sender_session.id,
                    "session_status": sender_session.status.value,
                    "error_type": type(exc).__name__,
                    "error": exc,
                },
            )
            raise HTTPException(status_code=409, detail="Не удалось синхронизировать чаты Telegram") from exc

        imported = 0
        target_chats = TargetChatRepository(self.db)
        for dialog in dialogs:
            chat_type = (
                TargetChatType.channel
                if bool(dialog["is_channel"]) and not bool(dialog["is_group"])
                else TargetChatType.supergroup
            )
            created = target_chats.upsert_synced_dialog(
                owner_telegram_id=telegram_user_id,
                session_id=sender_session.id,
                telegram_chat_id=int(dialog["telegram_chat_id"]),
                title=str(dialog["title"]),
                username=str(dialog["username"]) if dialog["username"] else None,
                chat_type=chat_type,
            )
            if created:
                imported += 1
        self.db.commit()
        return {"imported": imported, "total_dialogs": len(dialogs)}

    def list_chats(self, *, telegram_user_id: int) -> list[TargetChat]:
        return TargetChatRepository(self.db).list_enabled_for_owner(telegram_user_id)

    async def list_folders(self, *, telegram_user_id: int) -> list[DialogFolderOut]:
        sessions = TelegramSessionRepository(self.db).list_active_for_owner(telegram_user_id)
        if not sessions:
            return []

        rows_by_key: dict[tuple[int, str], DialogFolderOut] = {}
        for session in sessions:
            try:
                folders = await self.list_folders_from_session(session)
            except RuntimeError as exc:
                logger.warning("Telegram folder sync failed: session_id=%s error=%s", session.id, exc)
                await self.send_alert(
                    title="Telegram folder sync error",
                    status="409",
                    fields={
                        "action": "sync_folders",
                        "owner_telegram_id": telegram_user_id,
                        "session_id": session.id,
                        "session_status": session.status.value,
                        "error_type": type(exc).__name__,
                        "error": exc,
                    },
                )
                raise HTTPException(status_code=409, detail="Не удалось синхронизировать папки Telegram") from exc

            for folder in folders:
                key = (int(folder["id"]), str(folder["title"]))
                chat_ids = [int(chat_id) for chat_id in folder["telegram_chat_ids"]]
                if key not in rows_by_key:
                    rows_by_key[key] = DialogFolderOut(
                        id=key[0],
                        title=key[1],
                        telegram_chat_ids=[],
                    )
                current_ids = rows_by_key[key].telegram_chat_ids
                current_ids.extend(chat_id for chat_id in chat_ids if chat_id not in current_ids)

        self.db.commit()
        return list(rows_by_key.values())
