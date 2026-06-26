from __future__ import annotations

from autopost_manager.schedule import WeekdaySet


def test_weekday_set_parses_storage_value() -> None:
    weekdays = WeekdaySet.parse_storage_value("1,2,nope,2,9,0")

    assert weekdays.as_list() == [0, 1, 2]
    assert weekdays.serialize_for_storage() == "0,1,2"


def test_weekday_set_handles_empty_values() -> None:
    assert WeekdaySet.parse_storage_value(None).as_list() == []
    assert WeekdaySet.from_request([]).serialize_for_storage() is None
