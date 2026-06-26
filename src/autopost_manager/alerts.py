from __future__ import annotations

from datetime import UTC, datetime
from html import escape
import logging

from aiogram import Bot

from autopost_manager.config import get_settings

logger = logging.getLogger(__name__)


def compact(value: object, limit: int = 240) -> str:
    text = "—" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def alert_text(*, title: str, fields: dict[str, object], status: str = "error") -> str:
    lines = [
        "<b>Autopost alert</b>",
        f"<b>{escape(title)}</b>",
        f"<b>Status:</b> {escape(status)}",
        f"<b>Time:</b> {datetime.now(UTC).isoformat(timespec='seconds')}",
    ]
    for key, value in fields.items():
        lines.append(f"<b>{escape(key)}:</b> {escape(compact(value))}")
    return "\n".join(lines)


async def send_alert(*, title: str, fields: dict[str, object], status: str = "error") -> None:
    try:
        settings = get_settings()
        if settings.app_env == "test":
            return
        chat_ids = settings.alert_ids
        if not chat_ids:
            return

        bot = Bot(token=settings.bot_token)
        text = alert_text(title=title, fields=fields, status=status)
        try:
            for chat_id in chat_ids:
                try:
                    await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
                except Exception as exc:
                    logger.warning("Could not send alert: chat_id=%s error=%s", chat_id, exc)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Alert delivery failed before completion: error=%s", exc)
