from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from autopost_manager.schemas import PostCreate, PostScheduleUpdate


def test_post_create_rejects_too_many_targets() -> None:
    with pytest.raises(ValidationError):
        PostCreate(
            title="Title",
            body="Body",
            target_chat_ids=[uuid.uuid4() for _ in range(16)],
        )


def test_post_create_normalizes_weekdays_and_validates_timezone() -> None:
    post = PostCreate(title="Title", body="Body", schedule_weekdays=[3, 1, 3], timezone="UTC")

    assert post.schedule_weekdays == [1, 3]

    with pytest.raises(ValidationError):
        PostCreate(title="Title", body="Body", timezone="not-a-zone")


def test_post_schedule_update_rejects_invalid_weekday() -> None:
    with pytest.raises(ValidationError):
        PostScheduleUpdate(
            default_session_id=uuid.uuid4(),
            target_chat_ids=[uuid.uuid4()],
            schedule_weekdays=[7],
        )


def test_post_create_rejects_unsupported_parse_mode_and_session_strategy() -> None:
    with pytest.raises(ValidationError):
        PostCreate(title="Title", body="Body", parse_mode="markdown")

    with pytest.raises(ValidationError):
        PostCreate(title="Title", body="Body", session_strategy="round-robin")
