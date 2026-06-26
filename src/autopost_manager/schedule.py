from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


def as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class WeekdaySet:
    values: frozenset[int]

    @classmethod
    def parse_storage_value(cls, raw_value: str | None) -> WeekdaySet:
        if not raw_value:
            return cls(frozenset())
        days: set[int] = set()
        for item in raw_value.split(","):
            try:
                day = int(item)
            except ValueError:
                continue
            if 0 <= day <= 6:
                days.add(day)
        return cls(frozenset(days))

    @classmethod
    def from_request(cls, values: list[int] | None) -> WeekdaySet:
        if not values:
            return cls(frozenset())
        return cls(frozenset(int(value) for value in values if 0 <= int(value) <= 6))

    def serialize_for_storage(self) -> str | None:
        if not self.values:
            return None
        return ",".join(str(day) for day in sorted(self.values))

    def as_list(self) -> list[int]:
        return sorted(self.values)


def advance_by_days_until_future(start: datetime, now: datetime, days: int) -> datetime:
    candidate = as_utc_aware(start)
    reference = as_utc_aware(now)
    while candidate <= reference:
        candidate += timedelta(days=days)
    return candidate


def next_same_time_on_weekdays(
    start: datetime,
    now: datetime,
    weekdays: WeekdaySet,
) -> datetime | None:
    if not weekdays.values:
        return None
    candidate = as_utc_aware(start)
    reference = as_utc_aware(now)
    for _ in range(15):
        candidate += timedelta(days=1)
        if candidate > reference and candidate.weekday() in weekdays.values:
            return candidate
    return None
