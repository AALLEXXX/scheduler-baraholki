from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import aiohttp
from telethon import TelegramClient

from autopost_manager.config import get_settings
from autopost_manager.telegram_runtime import telegram_timeout


async def send_files_with_optional_text(
    *,
    client: TelegramClient,
    chat_id: int,
    files: list[str],
    text: str,
    parse_mode: str | None,
) -> Any:
    caption = text if text and len(text) <= 1024 else None
    sent = await telegram_timeout(
        client.send_file(
            chat_id,
            files[0] if len(files) == 1 else files,
            caption=caption,
            parse_mode=parse_mode,
        ),
        180,
    )
    if text and not caption:
        return await telegram_timeout(client.send_message(chat_id, text, parse_mode=parse_mode))
    return sent


def extract_sent_message_id(sent: Any) -> int:
    if isinstance(sent, list):
        return int(sent[-1].id)
    return int(sent.id)


async def download_bot_file(file_id: str, media_type: str) -> str:
    settings = get_settings()
    suffix_by_type = {
        "photo": ".jpg",
        "video": ".mp4",
        "animation": ".mp4",
        "document": "",
    }
    max_bytes = settings.max_bot_file_bytes
    timeout = aiohttp.ClientTimeout(total=120, sock_connect=20, sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout) as http:
        async with http.get(
            f"https://api.telegram.org/bot{settings.bot_token}/getFile",
            params={"file_id": file_id},
        ) as response:
            payload = await response.json()
            if not payload.get("ok"):
                raise RuntimeError(f"Could not resolve Telegram file: {payload}")
            file_path = payload["result"]["file_path"]

        suffix = Path(file_path).suffix or suffix_by_type.get(media_type, "")
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = temp.name

        async with http.get(
            f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"
        ) as response:
            if response.status >= 400:
                raise RuntimeError(f"Could not download Telegram file: HTTP {response.status}")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                raise RuntimeError("Telegram file is too large")
            downloaded = 0
            with Path(temp_path).open("wb") as output:
                async for chunk in response.content.iter_chunked(1024 * 256):
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise RuntimeError("Telegram file is too large")
                    output.write(chunk)

    return temp_path
