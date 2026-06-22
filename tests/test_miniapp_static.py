from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINIAPP = ROOT / "miniapp"


def read(name: str) -> str:
    return (MINIAPP / name).read_text(encoding="utf-8")


def test_miniapp_javascript_has_valid_syntax() -> None:
    result = subprocess.run(
        ["node", "--check", str(MINIAPP / "app.js")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_miniapp_removes_manual_account_selector_and_uses_connected_account() -> None:
    html = read("index.html")
    js = read("app.js")

    assert "account-row" not in html
    assert 'select name="default_session_id"' not in html
    assert 'document.querySelector("select[name=default_session_id]")' not in js
    assert "const sessionId = connected[0]?.id;" in js


def test_miniapp_form_submit_keeps_form_reference_across_async_boundaries() -> None:
    js = read("app.js")

    assert "const formElement = event.currentTarget;" in js
    assert "formElement.reset();" in js
    assert "event.currentTarget.reset" not in js


def test_miniapp_uses_telegram_drafts_instead_of_free_text_composer() -> None:
    html = read("index.html")
    js = read("app.js")

    assert 'id="draft-picker"' in html
    assert 'id="open-bot"' in html
    assert 'id="refresh-drafts"' in html
    assert 'textarea name="body"' not in html
    assert "selectedDraftId" in js
    assert 'api(`posts/${draftId}/schedule`' in js
    assert "Отправьте пост боту" in js


def test_miniapp_can_paginate_and_delete_posts() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    for element_id in [
        "draft-pagination",
        "drafts-prev",
        "drafts-next",
        "posts-pagination",
        "posts-prev",
        "posts-next",
    ]:
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js

    assert "draftPageSize: 5" in js
    assert "queuePageSize: 5" in js
    assert "function deletePost" in js
    assert "function deletionMessage" in js
    assert "source_messages_found" in js
    assert "telegram_delete_errors" in js
    assert "не был сохранён message_id" in js
    assert 'method: "DELETE"' in js
    assert "confirmDeletePost" in js
    assert ".danger-button" in css


def test_miniapp_auto_syncs_groups_and_can_logout_account() -> None:
    html = read("index.html")
    js = read("app.js")

    assert 'id="logout-account"' in html
    assert "account/logout" in js
    assert "autoSyncGroups" in js
    assert "groupsSyncedOnInit" in js
    assert "syncGroups({ silent: true })" in js


def test_miniapp_group_search_and_pagination_markup_matches_script() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    for element_id in ["group-search", "group-picker", "group-pagination", "groups-prev", "groups-next"]:
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js

    assert "groupPageSize: 10" in js
    assert "function renderGroupPicker()" in js
    assert "selectedChatIds" in js
    assert ".pagination" in css
    assert "[hidden]" in css


def test_miniapp_spam_guard_is_visible_in_ui_and_payload() -> None:
    html = read("index.html")
    js = read("app.js")

    assert 'name="interval_minutes" type="number" min="20"' in html
    assert "Минимальный интервал повтора" in js
    assert "За частую отправку сообщений" in js
    assert "Я понимаю" in js
    assert "confirmSpamRiskIfNeeded" in js
    assert "spam_risk_acknowledged" in js


def test_miniapp_cache_bust_versions_match_for_css_and_js() -> None:
    html = read("index.html")
    versions = re.findall(r"[.?&]v=(\d{8}-\d)", html)

    assert versions
    assert len(set(versions)) == 1
