from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from autopost_manager import api as api_module
from autopost_manager.db import SessionLocal
from autopost_manager.models import Post, SessionStatus, TargetChat, TargetChatType

from conftest import make_chat, make_post, make_session


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


def test_start_login_creates_pending_session_without_real_telegram(
    client,
    auth_user,
    monkeypatch,
) -> None:
    auth_user(111)

    async def fake_request_login_code(session):
        assert session.phone == "+995000000000"
        return "phone-code-hash"

    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={
            "api_id": 38746276,
            "api_hash": "187f6d7fa52fcce76690624ec5952ca2",
            "phone": "+995000000000",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "code_needed"

    with SessionLocal() as db:
        session = db.query(api_module.TelegramSession).one()
        assert session.owner_telegram_id == 111
        assert session.status == SessionStatus.code_needed
        assert session.phone_code_hash == "phone-code-hash"


def test_start_login_updates_existing_session_and_reports_send_error(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    auth_user(111)
    existing = make_session(db_session, owner_id=111, phone="+995000000000")
    db_session.commit()

    async def fake_request_login_code(session):
        return "updated-hash"

    monkeypatch.setattr(api_module, "request_login_code", fake_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={
            "api_id": 111111,
            "api_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "phone": "+995000000000",
        },
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        sessions = db.query(api_module.TelegramSession).all()
        assert len(sessions) == 1
        assert sessions[0].id == existing.id
        assert sessions[0].api_id == 111111
        assert sessions[0].api_hash == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert sessions[0].phone_code_hash == "updated-hash"

    async def failing_request_login_code(_session):
        raise RuntimeError("telegram rejected phone")

    monkeypatch.setattr(api_module, "request_login_code", failing_request_login_code)

    response = client.post(
        "/api/account/start-login",
        json={
            "api_id": 222222,
            "api_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "phone": "+995111111111",
        },
    )

    assert response.status_code == 422
    assert "telegram rejected phone" in response.text


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
    assert "bad code" in response.text


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
    assert "wrong password" in response.text

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


def test_sync_chats_rejects_foreign_session_and_telegram_runtime_error(
    client,
    auth_user,
    db_session,
    monkeypatch,
) -> None:
    session = make_session(db_session, owner_id=111)
    db_session.commit()

    auth_user(222)
    response = client.post(f"/api/sessions/{session.id}/sync-chats")
    assert response.status_code == 404

    auth_user(111)

    async def failing_dialogs(_session):
        raise RuntimeError("Telegram session needs login")

    monkeypatch.setattr(api_module, "list_dialogs_from_session", failing_dialogs)
    response = client.post(f"/api/sessions/{session.id}/sync-chats")
    assert response.status_code == 409
    assert "needs login" in response.text


def test_create_chat_validates_owner_and_duplicate(client, auth_user, db_session) -> None:
    session = make_session(db_session, owner_id=111)
    foreign_session = make_session(db_session, owner_id=222)
    db_session.commit()
    auth_user(111)

    foreign = client.post(
        "/api/chats",
        json={
            "session_id": str(foreign_session.id),
            "telegram_chat_id": -1001,
            "title": "Foreign",
            "type": "supergroup",
        },
    )
    assert foreign.status_code == 404

    created = client.post(
        "/api/chats",
        json={
            "session_id": str(session.id),
            "telegram_chat_id": -1001,
            "title": "Manual group",
            "type": "supergroup",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["title"] == "Manual group"

    duplicate = client.post(
        "/api/chats",
        json={
            "session_id": str(session.id),
            "telegram_chat_id": -1001,
            "title": "Manual group",
            "type": "supergroup",
        },
    )
    assert duplicate.status_code == 409


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
