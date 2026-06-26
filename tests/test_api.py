from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from telethon.errors import PasswordHashInvalidError

from autopost_manager import api as api_module
from autopost_manager.db import SessionLocal
from autopost_manager.models import (
    JobStatus,
    Post,
    PostMedia,
    PostStatus,
    PublishJob,
    SessionStatus,
    TargetChat,
    TargetChatType,
    UserSettings,
)

from conftest import make_chat, make_job, make_media, make_post, make_session


def post_payload(session_id: str, chat_ids: list[str], **overrides):
    payload = {
        "title": "Тестовый пост",
        "body": "Текст тестового поста",
        "status": "scheduled",
        "schedule_kind": "once",
        "next_run_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "interval_minutes": None,
        "default_session_id": session_id,
        "target_chat_ids": chat_ids,
    }
    payload.update(overrides)
    return payload


def test_protected_routes_reject_missing_telegram_init_data(client) -> None:
    response = client.get("/api/sessions")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing init data"


def test_health_routes_are_public(client) -> None:
    assert client.get("/health").json()["ok"] is True
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/rest/autopost/health").json()["ok"] is True


def test_app_config_returns_bot_username(client) -> None:
    response = client.get("/api/app-config")

    assert response.status_code == 200
    assert response.json()["bot_username"] == "scheduler_baraholki_bot"


def test_rest_and_rpc_routes_are_available(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session, title="REST Group")
    db_session.commit()

    assert client.get("/rest/autopost/app-config").status_code == 200
    assert client.get("/rest/autopost/sessions").status_code == 200
    assert client.get("/rest/autopost/chats").status_code == 200

    response = client.post(
        "/rest/autopost/posts",
        json=post_payload(str(session.id), [str(chat.id)]),
    )
    assert response.status_code == 200, response.text
    post_id = response.json()["id"]

    pause = client.patch(f"/rpc/autopost/posts/{post_id}/pause")
    assert pause.status_code == 200, pause.text


def test_create_once_post_returns_200_and_persists_targets(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session, title="Барахолка Тбилиси")
    db_session.commit()

    response = client.post("/api/posts", json=post_payload(str(session.id), [str(chat.id)]))

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "scheduled"
    assert data["target_chat_ids"] == [str(chat.id)]
    assert data["media"] == []

    with SessionLocal() as db:
        post = db.get(Post, uuid.UUID(data["id"]))
        assert post is not None
        assert post.created_by_telegram_id == 111
        assert [target.target_chat_id for target in post.targets] == [chat.id]


def test_create_interval_post_enforces_spam_limits(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    db_session.commit()

    too_fast = client.post(
        "/api/posts",
        json=post_payload(
            str(session.id),
            [str(chat.id)],
            schedule_kind="interval",
            interval_minutes=10,
        ),
    )
    assert too_fast.status_code == 422
    assert "20 минут" in too_fast.text

    missing_ack = client.post(
        "/api/posts",
        json=post_payload(
            str(session.id),
            [str(chat.id)],
            schedule_kind="interval",
            interval_minutes=20,
        ),
    )
    assert missing_ack.status_code == 422
    assert "Подтвердите риск" in missing_ack.text

    accepted = client.post(
        "/api/posts",
        json=post_payload(
            str(session.id),
            [str(chat.id)],
            schedule_kind="interval",
            interval_minutes=20,
            spam_risk_acknowledged=True,
        ),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["interval_minutes"] == 20


def test_create_post_rejects_more_than_fifteen_targets(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chats = [make_chat(db_session, session, title=f"Group {index}") for index in range(16)]
    db_session.commit()

    response = client.post(
        "/api/posts",
        json=post_payload(str(session.id), [str(chat.id) for chat in chats]),
    )

    assert response.status_code == 422
    assert "не больше 15" in response.text


def test_create_custom_weekdays_post_requires_and_returns_days(
    client,
    auth_user,
    db_session,
) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    db_session.commit()

    missing_days = client.post(
        "/api/posts",
        json=post_payload(
            str(session.id),
            [str(chat.id)],
            schedule_kind="custom_weekdays",
            schedule_weekdays=[],
        ),
    )
    assert missing_days.status_code == 422
    assert "день недели" in missing_days.text

    accepted = client.post(
        "/api/posts",
        json=post_payload(
            str(session.id),
            [str(chat.id)],
            schedule_kind="custom_weekdays",
            schedule_weekdays=[0, 2, 4],
        ),
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["schedule_kind"] == "custom_weekdays"
    assert accepted.json()["schedule_weekdays"] == [0, 2, 4]


def test_create_post_rejects_foreign_session_and_chat(client, auth_user, db_session) -> None:
    auth_user(222)
    foreign_session = make_session(db_session, owner_id=111)
    foreign_chat = make_chat(db_session, foreign_session)
    own_session = make_session(db_session, owner_id=222)
    db_session.commit()

    foreign_session_response = client.post(
        "/api/posts",
        json=post_payload(str(foreign_session.id), [str(foreign_chat.id)]),
    )
    assert foreign_session_response.status_code == 404
    assert "Telegram account not found" in foreign_session_response.text

    foreign_chat_response = client.post(
        "/api/posts",
        json=post_payload(str(own_session.id), [str(foreign_chat.id)]),
    )
    assert foreign_chat_response.status_code == 404
    assert "Group not found" in foreign_chat_response.text


def test_list_endpoints_are_scoped_to_authenticated_user(client, auth_user, db_session) -> None:
    session_111 = make_session(db_session, owner_id=111, phone="+111")
    chat_111 = make_chat(db_session, session_111, title="Owner group")
    make_post(db_session, owner_id=111, session=session_111, chats=[chat_111], body="Owner post")

    session_222 = make_session(db_session, owner_id=222, phone="+222")
    chat_222 = make_chat(db_session, session_222, title="Other group")
    make_post(db_session, owner_id=222, session=session_222, chats=[chat_222], body="Other post")
    db_session.commit()

    auth_user(111)
    sessions = client.get("/api/sessions").json()
    chats = client.get("/api/chats").json()
    posts = client.get("/api/posts").json()

    assert [session["phone"] for session in sessions] == ["+111"]
    assert [chat["title"] for chat in chats] == ["Owner group"]
    assert [post["body"] for post in posts] == ["Owner post"]


def test_list_posts_includes_telegram_media_for_drafts(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        status=api_module.PostStatus.draft,
        body="<b>Draft</b>",
    )
    make_media(db_session, post, media_type="photo", file_id="photo-file-id")
    db_session.commit()

    auth_user(111)
    response = client.get("/api/posts")

    assert response.status_code == 200
    [draft] = response.json()
    assert draft["status"] == "draft"
    assert draft["media"][0]["media_type"] == "photo"
    assert draft["media"][0]["file_id"] == "photo-file-id"


def test_start_login_creates_pending_session_without_real_telegram(
    client,
    auth_user,
    monkeypatch,
) -> None:
    auth_user(111)

    async def fake_request_login_code(session, *, force_sms=False):
        assert session.phone == "+995000000000"
        assert force_sms is False
        return SimpleNamespace(
            phone_code_hash="phone-code-hash",
            delivery_type="SentCodeTypeApp",
            next_delivery_type="SentCodeTypeSms",
            timeout=60,
        )

    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+995000000000"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "code_needed"
    assert response.json()["delivery_type"] == "SentCodeTypeApp"

    with SessionLocal() as db:
        session = db.query(api_module.TelegramSession).one()
        assert session.owner_telegram_id == 111
        assert session.api_id == 123456
        assert session.api_hash == "0123456789abcdef0123456789abcdef"
        assert session.status == SessionStatus.code_needed
        assert session.phone_code_hash == "phone-code-hash"


def test_start_login_rejects_invalid_phone_before_telegram(
    client,
    auth_user,
    monkeypatch,
) -> None:
    auth_user(111)

    async def unexpected_request_login_code(_session, *, force_sms=False):
        raise AssertionError("Telegram should not be called for invalid phone")

    monkeypatch.setattr(api_module, "request_login_code", unexpected_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "999"},
    )

    assert response.status_code == 422
    assert "код страны" in response.text or "номер телефона" in response.text


def test_start_login_normalizes_phone_before_telegram(
    client,
    auth_user,
    monkeypatch,
) -> None:
    auth_user(111)

    async def fake_request_login_code(session, *, force_sms=False):
        assert session.phone == "+18286637535"
        return SimpleNamespace(
            phone_code_hash="phone-code-hash",
            delivery_type="SentCodeTypeApp",
            next_delivery_type=None,
            timeout=60,
        )

    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+1 (828) 663-7535"},
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        session = db.query(api_module.TelegramSession).one()
        assert session.phone == "+18286637535"


def test_start_login_reuses_session_with_legacy_spaced_phone(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    auth_user(111)
    existing = make_session(
        db_session,
        owner_id=111,
        name="tg_111_86637535",
        phone="+1 828 663 7535",
        status=SessionStatus.revoked,
    )
    db_session.commit()

    async def fake_request_login_code(session, *, force_sms=False):
        assert session.id == existing.id
        assert session.phone == "+18286637535"
        return SimpleNamespace(
            phone_code_hash="phone-code-hash",
            delivery_type="SentCodeTypeApp",
            next_delivery_type=None,
            timeout=60,
        )

    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+1 (828) 663-7535"},
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        sessions = db.query(api_module.TelegramSession).all()
        assert len(sessions) == 1
        assert sessions[0].phone == "+18286637535"
        assert sessions[0].status == SessionStatus.code_needed


def test_start_login_uses_full_phone_for_session_name(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    auth_user(111)
    make_session(db_session, owner_id=111, name="tg_111_86637535", phone="+99586637535")
    db_session.commit()

    async def fake_request_login_code(session, *, force_sms=False):
        assert session.name == "tg_111_18286637535"
        assert session.phone == "+18286637535"
        return SimpleNamespace(
            phone_code_hash="phone-code-hash",
            delivery_type="SentCodeTypeApp",
            next_delivery_type=None,
            timeout=60,
        )

    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+1 (828) 663-7535"},
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        sessions = db.query(api_module.TelegramSession).order_by(api_module.TelegramSession.created_at).all()
        assert len(sessions) == 2
        assert sessions[1].name == "tg_111_18286637535"


def test_start_login_updates_existing_session_and_reports_send_error(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    auth_user(111)
    existing = make_session(db_session, owner_id=111, phone="+995000000000")
    db_session.commit()
    alerts: list[dict] = []

    async def fake_send_alert(**kwargs):
        alerts.append(kwargs)

    async def fake_request_login_code(session, *, force_sms=False):
        assert force_sms is True
        return SimpleNamespace(
            phone_code_hash="updated-hash",
            delivery_type="SentCodeTypeSms",
            next_delivery_type=None,
            timeout=None,
        )

    monkeypatch.setattr(api_module, "send_alert", fake_send_alert)
    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+995000000000", "force_sms": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["delivery_type"] == "SentCodeTypeSms"
    with SessionLocal() as db:
        sessions = db.query(api_module.TelegramSession).all()
        assert len(sessions) == 1
        assert sessions[0].id == existing.id
        assert sessions[0].api_id == 123456
        assert sessions[0].api_hash == "0123456789abcdef0123456789abcdef"
        assert sessions[0].phone_code_hash == "updated-hash"

    async def failing_request_login_code(_session, *, force_sms=False):
        raise RuntimeError("telegram rejected phone")

    monkeypatch.setattr(api_module, "request_login_code", failing_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+995111111111"},
    )

    assert response.status_code == 422
    assert "Не удалось отправить код Telegram" in response.text
    assert "telegram rejected phone" not in response.text
    assert len(alerts) == 1
    assert alerts[0]["title"] == "Telegram login error"
    assert alerts[0]["fields"]["action"] == "start-login"
    assert alerts[0]["fields"]["owner_telegram_id"] == 111
    assert alerts[0]["fields"]["error_type"] == "RuntimeError"


def test_start_login_enforces_code_request_cooldown(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    auth_user(111)
    existing = make_session(db_session, owner_id=111, phone="+995000000000")
    existing.last_code_requested_at = datetime.now(UTC)
    db_session.commit()

    async def unexpected_request_login_code(_session, *, force_sms=False):
        raise AssertionError("Telegram should not be called while cooldown is active")

    monkeypatch.setattr(api_module, "request_login_code", unexpected_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+995000000000", "force_sms": True},
    )

    assert response.status_code == 429
    assert "Повторно запросить код можно" in response.text


def test_start_login_cooldown_blocks_all_code_requests(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    auth_user(111)
    existing = make_session(db_session, owner_id=111, phone="+995000000000")
    existing.last_code_requested_at = datetime.now(UTC)
    db_session.commit()

    async def unexpected_request_login_code(_session, *, force_sms=False):
        raise AssertionError("Telegram should not be called while cooldown is active")

    monkeypatch.setattr(api_module, "request_login_code", unexpected_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={"phone": "+995000000000"},
    )

    assert response.status_code == 429
    assert "Повторно запросить код можно" in response.text


def test_confirm_code_handles_password_needed_and_success(client, auth_user, db_session, monkeypatch) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111, status=SessionStatus.code_needed)
    session.phone_code_hash = "hash"
    db_session.commit()

    async def fake_password_needed(_session, code):
        assert code == "12345"
        return False, None

    monkeypatch.setattr(api_module, "confirm_login_code", fake_password_needed)

    response = client.post(
        "/api/account/confirm-code",
        json={"session_id": str(session.id), "code": "12345"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "password_needed"

    class Me:
        id = 777
        username = "connected"

    async def fake_success(_session, code):
        return True, Me()

    monkeypatch.setattr(api_module, "confirm_login_code", fake_success)

    response = client.post(
        "/api/account/confirm-code",
        json={"session_id": str(session.id), "code": "54321"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"

    with SessionLocal() as db:
        refreshed = db.get(api_module.TelegramSession, session.id)
        assert refreshed.telegram_user_id == 777
        assert refreshed.username == "connected"
        assert refreshed.status == SessionStatus.active


def test_confirm_code_rejects_missing_foreign_and_telegram_errors(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111, status=SessionStatus.code_needed)
    db_session.commit()

    auth_user(222)
    response = client.post(
        "/api/account/confirm-code",
        json={"session_id": str(session.id), "code": "12345"},
    )
    assert response.status_code == 404

    auth_user(111)

    async def failing_confirm_login_code(_session, _code):
        raise RuntimeError("bad code")

    monkeypatch.setattr(api_module, "confirm_login_code", failing_confirm_login_code)
    response = client.post(
        "/api/account/confirm-code",
        json={"session_id": str(session.id), "code": "00000"},
    )
    assert response.status_code == 422
    assert "Не удалось подтвердить код Telegram" in response.text
    assert "bad code" not in response.text


def test_confirm_password_success_foreign_and_telegram_error(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111, status=SessionStatus.password_needed)
    db_session.commit()

    auth_user(222)
    response = client.post(
        "/api/account/confirm-password",
        json={"session_id": str(session.id), "password": "secret"},
    )
    assert response.status_code == 404

    auth_user(111)

    async def failing_confirm_password(_session, _password):
        raise RuntimeError("wrong password")

    monkeypatch.setattr(api_module, "confirm_login_password", failing_confirm_password)
    response = client.post(
        "/api/account/confirm-password",
        json={"session_id": str(session.id), "password": "bad"},
    )
    assert response.status_code == 422
    assert "Не удалось подтвердить пароль 2FA" in response.text
    assert "wrong password" not in response.text

    async def invalid_telegram_password(_session, _password):
        raise PasswordHashInvalidError(request=None)

    monkeypatch.setattr(api_module, "confirm_login_password", invalid_telegram_password)
    invalid_response = client.post(
        "/api/account/confirm-password",
        json={"session_id": str(session.id), "password": "bad"},
    )
    assert invalid_response.status_code == 422
    assert "облачный пароль" in invalid_response.text

    class Me:
        id = 888
        username = "passworduser"

    async def success_confirm_password(_session, password):
        assert password == "secret"
        return Me()

    monkeypatch.setattr(api_module, "confirm_login_password", success_confirm_password)
    response = client.post(
        "/api/account/confirm-password",
        json={"session_id": str(session.id), "password": "secret"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"

    with SessionLocal() as db:
        refreshed = db.get(api_module.TelegramSession, session.id)
        assert refreshed.telegram_user_id == 888
        assert refreshed.username == "passworduser"
        assert refreshed.phone_code_hash is None


def test_sync_chats_imports_and_updates_owned_dialogs(client, auth_user, db_session, monkeypatch) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    db_session.commit()

    async def fake_dialogs(_session):
        return [
            {
                "telegram_chat_id": -1001,
                "title": "Old Title",
                "username": "old",
                "is_group": True,
                "is_channel": False,
            },
            {
                "telegram_chat_id": -1002,
                "title": "Channel Title",
                "username": None,
                "is_group": False,
                "is_channel": True,
            },
        ]

    monkeypatch.setattr(api_module, "list_dialogs_from_session", fake_dialogs)

    response = client.post(f"/api/sessions/{session.id}/sync-chats")
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 2, "total_dialogs": 2}

    async def changed_dialogs(_session):
        return [
            {
                "telegram_chat_id": -1001,
                "title": "New Title",
                "username": "new",
                "is_group": True,
                "is_channel": False,
            }
        ]

    monkeypatch.setattr(api_module, "list_dialogs_from_session", changed_dialogs)

    response = client.post(f"/api/sessions/{session.id}/sync-chats")
    assert response.status_code == 200
    assert response.json() == {"imported": 0, "total_dialogs": 1}

    with SessionLocal() as db:
        chats = db.query(TargetChat).order_by(TargetChat.telegram_chat_id).all()
        assert len(chats) == 2
        assert chats[0].title == "Channel Title"
        assert chats[0].type == TargetChatType.channel
        assert chats[1].title == "New Title"
        assert chats[1].username == "new"


def test_logout_soft_pauses_without_deleting_session(
    client,
    auth_user,
    db_session,
    tmp_path,
) -> None:
    session_file = tmp_path / "telegram.session"
    session_file.write_text("secret", encoding="utf-8")
    session = make_session(db_session, owner_id=111)
    session.session_path = str(session_file)
    chat = make_chat(db_session, session, title="Visible group")
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    pending_job = make_job(db_session, post, chat, session=session, status=JobStatus.pending)
    other_session = make_session(db_session, owner_id=222)
    make_chat(db_session, other_session, title="Other group")
    db_session.commit()

    auth_user(111)
    response = client.post("/api/account/logout")

    assert response.status_code == 200
    assert response.json() == {"autopost_paused": True, "cancelled_jobs": 1}
    assert session_file.exists()
    assert client.get("/api/sessions").json()[0]["status"] == "active"
    assert client.get("/api/chats").json()
    assert client.get("/api/posts").json()
    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "cancelled"
    assert client.patch(f"/api/posts/{post.id}/pause").status_code == 409

    db_session.refresh(post)
    db_session.refresh(pending_job)
    assert post.status == PostStatus.scheduled
    assert pending_job.status == JobStatus.cancelled


def test_revoke_session_deletes_session_and_hides_user_data(
    client,
    auth_user,
    db_session,
    tmp_path,
    monkeypatch,
) -> None:
    session_file = tmp_path / "telegram.session"
    session_file.write_text("secret", encoding="utf-8")
    session = make_session(db_session, owner_id=111)
    session.session_path = str(session_file)
    session.session_string = "string-session"
    chat = make_chat(db_session, session, title="Visible group")
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    pending_job = make_job(db_session, post, chat, session=session, status=JobStatus.pending)
    db_session.commit()

    called = []

    async def fake_logout_session_from_telegram(logout_session):
        called.append(logout_session.id)

    monkeypatch.setattr(api_module, "logout_session_from_telegram", fake_logout_session_from_telegram)

    auth_user(111)
    response = client.post("/api/account/revoke-session")

    assert response.status_code == 200
    assert response.json() == {
        "revoked_sessions": 1,
        "disabled_chats": 1,
        "cancelled_jobs": 1,
        "telegram_logout_errors": [],
    }
    assert called == [session.id]
    assert not session_file.exists()
    assert client.get("/api/sessions").json()[0]["status"] == "revoked"
    assert client.get("/api/chats").json() == []
    assert client.get("/api/posts").json() == []
    assert client.get("/api/jobs").json() == []

    db_session.refresh(post)
    db_session.refresh(pending_job)
    db_session.refresh(session)
    assert post.status == PostStatus.paused
    assert pending_job.status == JobStatus.cancelled
    assert session.session_string is None
    assert db_session.get(UserSettings, 111).autopost_paused is True


def test_account_pause_and_resume_toggle_user_settings(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    make_job(db_session, post, chat, session=session, status=JobStatus.pending)
    db_session.commit()
    auth_user(111)

    pause_response = client.post("/api/account/pause")
    assert pause_response.status_code == 200
    assert pause_response.json() == {"autopost_paused": True, "cancelled_jobs": 1}
    assert client.get("/api/user-settings").json() == {"autopost_paused": True}

    blocked_response = client.post(
        f"/api/posts/{post.id}/schedule",
        json=post_payload(str(session.id), [str(chat.id)]),
    )
    assert blocked_response.status_code == 409
    assert "Автопостинг на паузе" in blocked_response.text

    resume_response = client.post("/api/account/resume")
    assert resume_response.status_code == 200
    assert resume_response.json() == {"autopost_paused": False, "cancelled_jobs": 0}
    assert client.get("/api/user-settings").json() == {"autopost_paused": False}


def test_queue_actions_require_active_account(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111, status=SessionStatus.revoked)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    db_session.commit()
    auth_user(111)

    assert client.get("/api/posts").json() == []
    assert client.get("/api/jobs").json() == []

    for response in [
        client.patch(f"/api/posts/{post.id}/pause"),
        client.patch(f"/api/posts/{post.id}/resume", json={}),
        client.post(f"/api/posts/{post.id}/enqueue-now"),
        client.delete(f"/api/posts/{post.id}"),
    ]:
        assert response.status_code == 409
        assert "Сначала подключите" in response.text


def test_sync_chats_rejects_foreign_session_and_telegram_runtime_error(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111)
    db_session.commit()
    alerts: list[dict] = []

    async def fake_send_alert(**kwargs):
        alerts.append(kwargs)

    auth_user(222)
    response = client.post(f"/api/sessions/{session.id}/sync-chats")
    assert response.status_code == 404

    auth_user(111)

    async def failing_dialogs(_session):
        raise RuntimeError("Telegram session needs login")

    monkeypatch.setattr(api_module, "send_alert", fake_send_alert)
    monkeypatch.setattr(api_module, "list_dialogs_from_session", failing_dialogs)
    response = client.post(f"/api/sessions/{session.id}/sync-chats")
    assert response.status_code == 409
    assert "Не удалось синхронизировать" in response.text
    assert "needs login" not in response.text
    assert len(alerts) == 1
    assert alerts[0]["title"] == "Telegram dialog sync error"
    assert alerts[0]["fields"]["action"] == "sync_chats"
    assert alerts[0]["fields"]["owner_telegram_id"] == 111
    assert alerts[0]["fields"]["session_id"] == session.id


def test_create_chat_validates_owner_and_duplicate(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    make_session(db_session, owner_id=222)
    db_session.commit()
    auth_user(111)

    response = client.post(
        "/api/chats",
        json={
            "session_id": str(session.id),
            "telegram_chat_id": -1001,
            "title": "Manual group",
            "type": "supergroup",
        },
    )
    assert response.status_code == 410
    assert "синхронизацию" in response.text


def test_list_folders_returns_telegram_folder_chat_ids_without_local_sync_filter(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111)
    first = make_chat(db_session, session, title="First", telegram_chat_id=-1001)
    second = make_chat(db_session, session, title="Second", telegram_chat_id=-1002)
    disabled = make_chat(db_session, session, title="Disabled", telegram_chat_id=-1003, enabled=False)
    other_session = make_session(db_session, owner_id=222)
    make_chat(db_session, other_session, title="Other", telegram_chat_id=-1004)
    db_session.commit()

    async def fake_folders(_session):
        return [
            {
                "id": 7,
                "title": "Барахолки",
                "telegram_chat_ids": [
                    first.telegram_chat_id,
                    second.telegram_chat_id,
                    disabled.telegram_chat_id,
                    -1004,
                ],
            },
            {"id": 8, "title": "Пустая", "telegram_chat_ids": [-999]},
        ]

    monkeypatch.setattr(api_module, "list_dialog_folders_from_session", fake_folders)
    auth_user(111)

    response = client.get("/api/folders")

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "id": 7,
            "title": "Барахолки",
            "telegram_chat_ids": [
                first.telegram_chat_id,
                second.telegram_chat_id,
                disabled.telegram_chat_id,
                -1004,
            ],
        },
        {"id": 8, "title": "Пустая", "telegram_chat_ids": [-999]},
    ]


def test_list_folders_keeps_folder_visible_before_chats_are_synced(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    make_session(db_session, owner_id=111)
    db_session.commit()

    async def fake_folders(_session):
        return [{"id": 7, "title": "Барахолки", "telegram_chat_ids": [-1001, -1002]}]

    monkeypatch.setattr(api_module, "list_dialog_folders_from_session", fake_folders)
    auth_user(111)

    response = client.get("/api/folders")

    assert response.status_code == 200, response.text
    assert response.json() == [{"id": 7, "title": "Барахолки", "telegram_chat_ids": [-1001, -1002]}]


def test_list_folders_reads_all_active_user_sessions(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    newer = make_session(db_session, owner_id=111, name="newer")
    older = make_session(db_session, owner_id=111, name="older")
    newer.updated_at = datetime.now(UTC)
    older.updated_at = datetime.now(UTC) - timedelta(days=1)
    chat = make_chat(db_session, older, telegram_chat_id=-1002)
    db_session.commit()

    called_session_names: list[str] = []

    async def fake_folders(session):
        called_session_names.append(session.name)
        if session.name == "newer":
            return []
        return [{"id": 9, "title": "Old account folder", "telegram_chat_ids": [chat.telegram_chat_id]}]

    monkeypatch.setattr(api_module, "list_dialog_folders_from_session", fake_folders)
    auth_user(111)

    response = client.get("/api/folders")

    assert response.status_code == 200, response.text
    assert called_session_names == ["newer", "older"]
    assert response.json() == [
        {"id": 9, "title": "Old account folder", "telegram_chat_ids": [chat.telegram_chat_id]}
    ]


def test_create_post_requires_interval_session_and_group(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    db_session.commit()

    missing_interval = client.post(
        "/api/posts",
        json=post_payload(
            str(session.id),
            [str(chat.id)],
            schedule_kind="interval",
            interval_minutes=None,
        ),
    )
    assert missing_interval.status_code == 422
    assert "Укажите интервал" in missing_interval.text

    missing_session = client.post(
        "/api/posts",
        json=post_payload(None, [str(chat.id)]),
    )
    assert missing_session.status_code == 422
    assert "Сначала подключите" in missing_session.text

    missing_group = client.post(
        "/api/posts",
        json=post_payload(str(session.id), []),
    )
    assert missing_group.status_code == 422
    assert "Выберите хотя бы одну группу" in missing_group.text


def test_schedule_existing_telegram_draft(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    draft = make_post(
        db_session,
        owner_id=111,
        session=None,
        chats=[],
        status=api_module.PostStatus.draft,
        body="<b>Telegram draft</b>",
    )
    make_media(db_session, draft, media_type="photo")
    db_session.commit()
    auth_user(111)

    response = client.post(
        f"/api/posts/{draft.id}/schedule",
        json={
            "schedule_kind": "once",
            "next_run_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "interval_minutes": None,
            "default_session_id": str(session.id),
            "target_chat_ids": [str(chat.id)],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "scheduled"
    assert data["default_session_id"] == str(session.id)
    assert data["target_chat_ids"] == [str(chat.id)]
    assert data["media"][0]["media_type"] == "photo"


def test_schedule_existing_post_edits_targets_and_cancels_pending_jobs(
    client,
    auth_user,
    db_session,
) -> None:
    session = make_session(db_session, owner_id=111)
    old_chat = make_chat(db_session, session, title="Old")
    new_chat = make_chat(db_session, session, title="New", telegram_chat_id=-1002)
    post = make_post(db_session, owner_id=111, session=session, chats=[old_chat])
    job = make_job(db_session, post, old_chat, session=session, status=JobStatus.pending)
    db_session.commit()
    auth_user(111)

    response = client.post(
        f"/api/posts/{post.id}/schedule",
        json={
            "schedule_kind": "interval",
            "next_run_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
            "interval_minutes": 45,
            "spam_risk_acknowledged": True,
            "default_session_id": str(session.id),
            "target_chat_ids": [str(new_chat.id)],
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "scheduled"
    assert data["schedule_kind"] == "interval"
    assert data["target_chat_ids"] == [str(new_chat.id)]

    db_session.refresh(job)
    db_session.refresh(post)
    assert job.status == JobStatus.cancelled
    assert [target.target_chat_id for target in post.targets] == [new_chat.id]


def test_pause_post_cancels_pending_jobs(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    pending = make_job(db_session, post, chat, session=session, status=JobStatus.pending)
    done = make_job(db_session, post, chat, session=session, status=JobStatus.done)
    db_session.commit()
    auth_user(111)

    response = client.patch(f"/api/posts/{post.id}/pause")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paused"
    db_session.refresh(pending)
    db_session.refresh(done)
    assert pending.status == JobStatus.cancelled
    assert done.status == JobStatus.done


def test_resume_paused_post_requires_future_date(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        status=PostStatus.paused,
        next_run_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    db_session.commit()
    auth_user(111)

    missing_date = client.patch(f"/api/posts/{post.id}/resume", json={})
    assert missing_date.status_code == 422
    assert "новую будущую дату" in missing_date.text

    response = client.patch(
        f"/api/posts/{post.id}/resume",
        json={"next_run_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "scheduled"


def test_schedule_existing_post_rejects_foreign_or_disabled_targets(
    client,
    auth_user,
    db_session,
) -> None:
    session = make_session(db_session, owner_id=111)
    disabled_chat = make_chat(db_session, session, enabled=False)
    foreign_session = make_session(db_session, owner_id=222)
    foreign_chat = make_chat(db_session, foreign_session)
    draft = make_post(db_session, owner_id=111, status=api_module.PostStatus.draft, chats=[])
    db_session.commit()
    auth_user(111)

    disabled = client.post(
        f"/api/posts/{draft.id}/schedule",
        json={
            "schedule_kind": "once",
            "next_run_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "default_session_id": str(session.id),
            "target_chat_ids": [str(disabled_chat.id)],
        },
    )
    assert disabled.status_code == 404

    foreign = client.post(
        f"/api/posts/{draft.id}/schedule",
        json={
            "schedule_kind": "once",
            "next_run_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "default_session_id": str(session.id),
            "target_chat_ids": [str(foreign_chat.id)],
        },
    )
    assert foreign.status_code == 404


def test_delete_post_removes_queue_rows_and_source_bot_messages(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(
        db_session,
        owner_id=111,
        session=session,
        chats=[chat],
        source_bot_chat_id=111,
        source_bot_message_id=40,
        ack_bot_chat_id=111,
        ack_bot_message_id=42,
    )
    make_media(db_session, post, source_bot_message_id=41)
    make_media(db_session, post, source_bot_message_id=40, order_index=1)
    make_job(db_session, post, chat, session=session)
    db_session.commit()

    calls: list[set[tuple[int, int]]] = []

    async def fake_delete_source_messages(
        *,
        telegram_user_id: int,
        refs: set[tuple[int, int]],
        db,
        match_texts: set[str] | None = None,
        ack_text: str | None = None,
        created_at=None,
        media_count: int = 0,
    ) -> api_module.BotMessageDeleteResult:
        assert telegram_user_id == 111
        assert db is not None
        assert match_texts == {"Post body"}
        assert ack_text == api_module.POST_SAVED_ACK_TEXT
        assert created_at is not None
        assert media_count == 2
        calls.append(refs)
        return api_module.BotMessageDeleteResult(attempted=len(refs), deleted=len(refs))

    monkeypatch.setattr(api_module, "delete_source_messages", fake_delete_source_messages)
    auth_user(111)

    response = client.delete(f"/api/posts/{post.id}")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "ok": True,
        "deleted_jobs": 1,
        "source_messages_found": 3,
        "telegram_delete_attempted": 3,
        "deleted_bot_messages": 3,
        "telegram_delete_errors": [],
    }
    assert calls == [{(111, 40), (111, 41), (111, 42)}]

    with SessionLocal() as db:
        assert db.get(Post, post.id) is None
        assert db.query(PostMedia).count() == 0
        assert db.query(PublishJob).count() == 0


def test_delete_post_is_scoped_to_owner(client, auth_user, db_session, monkeypatch) -> None:
    post = make_post(
        db_session,
        owner_id=222,
        source_bot_chat_id=222,
        source_bot_message_id=50,
    )
    db_session.commit()

    async def fail_delete_source_messages(
        *,
        telegram_user_id: int,
        refs: set[tuple[int, int]],
        db,
    ) -> api_module.BotMessageDeleteResult:
        assert telegram_user_id == 111
        assert refs
        assert db is not None
        raise AssertionError("foreign post should not reach Telegram delete")

    monkeypatch.setattr(api_module, "delete_source_messages", fail_delete_source_messages)
    auth_user(111)

    response = client.delete(f"/api/posts/{post.id}")

    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.get(Post, post.id) is not None


def test_delete_bot_messages_is_best_effort_and_closes_session(monkeypatch) -> None:
    calls: list[tuple[str, int | str, int | None]] = []

    class FakeSession:
        async def close(self) -> None:
            calls.append(("close", "session", None))

    class FakeBot:
        def __init__(self, token: str) -> None:
            calls.append(("init", token, None))
            self.session = FakeSession()

        async def delete_message(self, *, chat_id: int, message_id: int) -> None:
            calls.append(("delete", chat_id, message_id))
            if message_id == 2:
                raise RuntimeError("telegram refused deletion")

    monkeypatch.setattr(api_module, "Bot", FakeBot)

    empty = asyncio.run(api_module.delete_bot_messages(set()))
    assert empty == api_module.BotMessageDeleteResult()

    result = asyncio.run(api_module.delete_bot_messages({(100, 1), (100, 2)}))

    assert result.attempted == 2
    assert result.deleted == 1
    assert len(result.errors) == 1
    assert "telegram refused deletion" in result.errors[0]
    assert ("init", "1234567890:TEST_BOT_TOKEN_VALUE", None) in calls
    assert ("delete", 100, 1) in calls
    assert ("delete", 100, 2) in calls
    assert calls[-1] == ("close", "session", None)


def test_delete_source_messages_prefers_user_session_and_falls_back_to_bot(
    db_session,
    monkeypatch,
) -> None:
    make_session(db_session, owner_id=111)
    db_session.commit()

    calls: list[str] = []

    async def failing_user_delete(**_kwargs):
        calls.append("user")
        raise RuntimeError("user session refused")

    async def successful_bot_delete(refs: set[tuple[int, int]]) -> api_module.BotMessageDeleteResult:
        calls.append("bot")
        return api_module.BotMessageDeleteResult(attempted=len(refs), deleted=len(refs))

    monkeypatch.setattr(api_module, "delete_messages_from_session", failing_user_delete)
    monkeypatch.setattr(api_module, "delete_bot_messages", successful_bot_delete)

    result = asyncio.run(
        api_module.delete_source_messages(
            telegram_user_id=111,
            refs={(111, 10), (111, 11)},
            db=db_session,
        )
    )

    assert result.attempted == 4
    assert result.deleted == 2
    assert "user session refused" in result.errors[0]
    assert calls == ["user", "bot"]


def test_enqueue_now_and_jobs_are_scoped_to_owner(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])

    other_session = make_session(db_session, owner_id=222)
    other_chat = make_chat(db_session, other_session)
    other_post = make_post(db_session, owner_id=222, session=other_session, chats=[other_chat])
    db_session.commit()

    auth_user(111)
    response = client.post(f"/api/posts/{post.id}/enqueue-now")
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "jobs_created": 1}

    foreign = client.post(f"/api/posts/{other_post.id}/enqueue-now")
    assert foreign.status_code == 404

    jobs = client.get("/api/jobs")
    assert jobs.status_code == 200
    assert len(jobs.json()) == 1
    assert jobs.json()[0]["post_id"] == str(post.id)


def test_audit_lists_owner_jobs_with_post_and_target_details(
    client,
    auth_user,
    db_session,
) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session, title="Main Group", telegram_chat_id=-1009876543210)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat], body="Audit body")
    done_job = make_job(db_session, post, chat, session=session, status=JobStatus.done)
    done_job.telegram_message_id = 123
    failed_job = make_job(db_session, post, chat, session=session, status=JobStatus.failed)
    failed_job.last_error = "Telegram refused"

    other_session = make_session(db_session, owner_id=222)
    other_chat = make_chat(db_session, other_session, title="Other Group")
    other_post = make_post(db_session, owner_id=222, session=other_session, chats=[other_chat])
    make_job(db_session, other_post, other_chat, session=other_session, status=JobStatus.done)
    db_session.commit()

    auth_user(111)
    response = client.get("/api/audit?page=1&page_size=1")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] == 2
    assert len(data["items"]) == 1
    assert data["items"][0]["post_id"] == str(post.id)
    assert data["items"][0]["post_title"] == post.title
    assert data["items"][0]["post_preview"] == "Audit body"
    assert data["items"][0]["media_count"] == 0
    assert data["items"][0]["target_chat_title"] == "Main Group"
    if data["items"][0]["telegram_message_id"] == 123:
        assert data["items"][0]["message_link"] == "https://t.me/c/9876543210/123"
    assert data["items"][0]["status"] in {done_job.status.value, failed_job.status.value}


def test_audit_message_endpoint_fetches_exact_delivered_message(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session, title="Main Group", telegram_chat_id=-1009876543210)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat], body="Audit body")
    job = make_job(db_session, post, chat, session=session, status=JobStatus.done)
    job.telegram_message_id = 34
    db_session.commit()

    async def fake_get_message_from_session(*, session, peer, message_id):
        assert session.owner_telegram_id == 111
        assert peer == -1009876543210
        assert message_id == 34
        return SimpleNamespace(text="Exact delivered message", has_media=False, date=None)

    monkeypatch.setattr(api_module, "get_message_from_session", fake_get_message_from_session)
    auth_user(111)

    response = client.get(f"/api/audit/{job.id}/message")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": str(job.id),
        "target_chat_title": "Main Group",
        "telegram_message_id": 34,
        "message_text": "Exact delivered message",
        "message_link": "https://t.me/c/9876543210/34",
    }


def test_audit_requires_active_account(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111, status=SessionStatus.revoked)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    make_job(db_session, post, chat, session=session, status=JobStatus.done)
    db_session.commit()

    auth_user(111)
    response = client.get("/api/audit")

    assert response.status_code == 200
    assert response.json() == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_admin_can_view_user_audit(client, auth_user, db_session, monkeypatch) -> None:
    monkeypatch.setattr(api_module.get_settings(), "admin_telegram_ids", "999")
    target_session = make_session(db_session, owner_id=111, username="alice")
    target_chat = make_chat(db_session, target_session, title="Alice Group", telegram_chat_id=-1009876543210)
    target_post = make_post(db_session, owner_id=111, session=target_session, chats=[target_chat], body="Alice body")
    target_job = make_job(db_session, target_post, target_chat, session=target_session, status=JobStatus.done)
    target_job.telegram_message_id = 45

    other_session = make_session(db_session, owner_id=222)
    other_chat = make_chat(db_session, other_session, title="Other Group")
    other_post = make_post(db_session, owner_id=222, session=other_session, chats=[other_chat])
    make_job(db_session, other_post, other_chat, session=other_session, status=JobStatus.done)
    db_session.commit()

    auth_user(999)
    response = client.get("/api/admin/users/111/audit", params={"page": 1, "page_size": 20})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(target_job.id)
    assert data["items"][0]["post_preview"] == "Alice body"
    assert data["items"][0]["target_chat_title"] == "Alice Group"
    assert data["items"][0]["message_link"] == "https://t.me/c/9876543210/45"


def test_admin_can_view_user_audit_message(client, auth_user, db_session, monkeypatch) -> None:
    monkeypatch.setattr(api_module.get_settings(), "admin_telegram_ids", "999")
    target_session = make_session(db_session, owner_id=111, username="alice")
    target_chat = make_chat(db_session, target_session, title="Alice Group", telegram_chat_id=-1009876543210)
    target_post = make_post(db_session, owner_id=111, session=target_session, chats=[target_chat], body="Alice body")
    target_job = make_job(db_session, target_post, target_chat, session=target_session, status=JobStatus.done)
    target_job.telegram_message_id = 45
    db_session.commit()

    async def fake_get_message_from_session(*, session, peer, message_id):
        assert session.owner_telegram_id == 111
        assert peer == -1009876543210
        assert message_id == 45
        return SimpleNamespace(text="Alice delivered message", has_media=False, date=None)

    monkeypatch.setattr(api_module, "get_message_from_session", fake_get_message_from_session)

    auth_user(999)
    response = client.get(f"/api/admin/users/111/audit/{target_job.id}/message")

    assert response.status_code == 200, response.text
    assert response.json()["message_text"] == "Alice delivered message"


def test_admin_user_audit_requires_admin(client, auth_user, db_session) -> None:
    target_session = make_session(db_session, owner_id=111)
    target_chat = make_chat(db_session, target_session)
    target_post = make_post(db_session, owner_id=111, session=target_session, chats=[target_chat])
    make_job(db_session, target_post, target_chat, session=target_session, status=JobStatus.done)
    db_session.commit()

    auth_user(222)
    response = client.get("/api/admin/users/111/audit")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_endpoints_require_configured_admin(client, auth_user, db_session) -> None:
    auth_user(111)
    make_session(db_session, owner_id=111, username="regular")
    db_session.commit()

    response = client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_app_config_marks_configured_admin(client, monkeypatch) -> None:
    monkeypatch.setattr(api_module.get_settings(), "admin_telegram_ids", "7569215208")
    api_module.app.dependency_overrides[api_module.optional_telegram_user_id] = lambda: 7569215208

    response = client.get("/api/app-config")

    assert response.status_code == 200
    assert response.json()["is_admin"] is True


def test_admin_lists_users_with_search_and_pagination(client, auth_user, db_session, monkeypatch) -> None:
    monkeypatch.setattr(api_module.get_settings(), "admin_telegram_ids", "999")
    auth_user(999)
    first = make_session(db_session, owner_id=111, username="alice_market", phone="+111")
    second = make_session(db_session, owner_id=222, username="bob_shop", phone="+222")
    db_session.add(UserSettings(telegram_user_id=111, autopost_paused=True, daily_send_limit=7))
    chat = make_chat(db_session, first, title="Main")
    post = make_post(db_session, owner_id=111, session=first, chats=[chat])
    make_job(db_session, post, chat, session=first, status=JobStatus.done)
    make_job(db_session, post, chat, session=first, status=JobStatus.failed)
    db_session.commit()

    response = client.get("/api/admin/users", params={"query": "alice", "page": 1, "page_size": 1})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] == 1
    assert data["items"][0]["telegram_user_id"] == 111
    assert data["items"][0]["username"] == "alice_market"
    assert data["items"][0]["phone"] == "+***"
    assert data["items"][0]["autopost_paused"] is True
    assert data["items"][0]["banned"] is False
    assert data["items"][0]["daily_send_limit"] == 7
    assert data["items"][0]["sent_today"] == 1
    assert data["items"][0]["failed_total"] == 1
    assert second.username == "bob_shop"


def test_admin_updates_user_controls(client, auth_user, db_session, monkeypatch) -> None:
    monkeypatch.setattr(api_module.get_settings(), "admin_telegram_ids", "999")
    auth_user(999)
    make_session(db_session, owner_id=111, username="alice")
    db_session.commit()

    response = client.patch(
        "/api/admin/users/111",
        json={"banned": True, "autopost_paused": True, "daily_send_limit": 3},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["telegram_user_id"] == 111
    assert data["banned"] is True
    assert data["autopost_paused"] is True
    assert data["daily_send_limit"] == 3
    with SessionLocal() as db:
        settings = db.get(UserSettings, 111)
        assert settings.banned is True
        assert settings.autopost_paused is True
        assert settings.daily_send_limit == 3


def test_banned_user_cannot_schedule_posts(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    db_session.add(UserSettings(telegram_user_id=111, banned=True))
    db_session.commit()

    response = client.post("/api/posts", json=post_payload(str(session.id), [str(chat.id)]))

    assert response.status_code == 403
    assert "заблокирован" in response.text


def test_daily_send_limit_blocks_new_schedules_after_sent_jobs(client, auth_user, db_session) -> None:
    auth_user(111)
    session = make_session(db_session, owner_id=111)
    chat = make_chat(db_session, session)
    post = make_post(db_session, owner_id=111, session=session, chats=[chat])
    make_job(db_session, post, chat, session=session, status=JobStatus.done)
    db_session.add(UserSettings(telegram_user_id=111, daily_send_limit=1))
    db_session.commit()

    response = client.post("/api/posts", json=post_payload(str(session.id), [str(chat.id)]))

    assert response.status_code == 429
    assert "дневной лимит" in response.text


def test_admin_statistics_returns_global_delivery_metrics(client, auth_user, db_session, monkeypatch) -> None:
    monkeypatch.setattr(api_module.get_settings(), "admin_telegram_ids", "999")
    auth_user(999)
    first = make_session(db_session, owner_id=111)
    second = make_session(db_session, owner_id=222)
    chat = make_chat(db_session, first)
    other_chat = make_chat(db_session, second)
    post = make_post(db_session, owner_id=111, session=first, chats=[chat])
    other_post = make_post(db_session, owner_id=222, session=second, chats=[other_chat])
    old_done = make_job(
        db_session,
        post,
        chat,
        session=first,
        status=JobStatus.done,
        due_at=datetime.now(UTC) - timedelta(days=40),
    )
    old_done.updated_at = datetime.now(UTC) - timedelta(days=40)
    done_today = make_job(db_session, post, chat, session=first, status=JobStatus.done)
    done_today.updated_at = datetime.now(UTC)
    failed_today = make_job(db_session, other_post, other_chat, session=second, status=JobStatus.failed)
    failed_today.updated_at = datetime.now(UTC)
    db_session.commit()

    response = client.get("/api/admin/stats")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sent_total"] == 2
    assert data["sent_today"] == 1
    assert data["sent_week"] == 1
    assert data["sent_month"] == 1
    assert data["failed_total"] == 1
    assert data["users_total"] == 2
    assert data["daily_active_users"] == 1
