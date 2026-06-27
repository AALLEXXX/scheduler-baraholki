from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from autopost_manager.models import ParseMode as ParseMode
from autopost_manager.models import SessionStrategy as SessionStrategy

MAX_TARGET_CHAT_IDS = 15
MAX_SCHEDULE_WEEKDAYS = 7


def normalize_schedule_weekdays(values: list[int]) -> list[int]:
    invalid = [value for value in values if value < 0 or value > 6]
    if invalid:
        raise ValueError("Дни недели должны быть числами от 0 до 6")
    return sorted(set(values))


def ensure_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Укажите корректную IANA timezone") from exc
    return value
