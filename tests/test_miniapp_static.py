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


def test_miniapp_login_only_asks_for_phone_number() -> None:
    html = read("index.html")
    js = read("app.js")

    assert 'name="phone"' in html
    assert 'name="api_id"' not in html
    assert 'name="api_hash"' not in html
    assert "API ID" not in html
    assert "API Hash" not in html
    assert "Введите номер телефона" in html
    assert "api_id" not in js
    assert "api_hash" not in js


def test_miniapp_form_submit_keeps_form_reference_across_async_boundaries() -> None:
    js = read("app.js")

    assert "const formElement = event.currentTarget;" in js
    assert "formElement.reset();" in js
    assert "event.currentTarget.reset" not in js


def test_miniapp_uses_telegram_drafts_instead_of_free_text_composer() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    assert 'id="draft-picker"' in html
    assert 'id="open-bot"' not in html
    assert 'id="refresh-drafts"' not in html
    assert 'id="sync-groups"' not in html
    assert "Открыть бота и создать пост" not in html
    assert "появится здесь как черновик" in html
    assert "Отправьте готовый пост прямо в чат" in html
    assert "draft-instruction" in html
    assert 'textarea name="body"' not in html
    assert "selectedDraftId" in js
    assert 'api(`posts/${draftId}/schedule`' in js
    assert "Отправьте пост боту" in js
    assert "openTelegramBot" not in js
    assert "tg://resolve" not in js
    assert "#open-bot" not in js
    assert "#refresh-drafts" not in js
    assert "#sync-groups" not in js
    assert ".draft-instruction" in css


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


def test_miniapp_queue_has_russian_details_editing_and_pause_controls() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    for element_id in [
        "edit-modal",
        "edit-form",
        "edit-group-search",
        "edit-folder-picker",
        "edit-group-picker",
        "edit-save",
    ]:
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js

    assert "Расписание" in js
    assert "Куда" in js
    assert "Запланирован" in js
    assert "На паузе" in js
    assert "Редактировать" in js
    assert "Пауза" in js
    assert "Продолжить" in js
    assert "togglePausePost" in js
    assert "openEditPost" in js
    assert 'method: "PATCH"' in js
    assert "/pause" in js
    assert "/resume" in js
    assert "Старая дата уже прошла" in js
    assert ".post-meta" in css
    assert ".post-item.scheduled" in css
    assert ".modal-backdrop" in css
    assert ".modal-close" in css
    assert 'id="edit-close" class="modal-close"' in html


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

    for element_id in [
        "group-search",
        "folder-picker",
        "group-picker",
        "group-pagination",
        "groups-prev",
        "groups-next",
    ]:
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js

    assert "groupPageSize: 10" in js
    assert "selectedFolderId" in js
    assert 'api("folders")' in js
    assert "function renderFolderPicker" in js
    assert ".folder-chip" in css
    assert "function renderGroupPicker()" in js
    assert "selectedChatIds" in js
    assert "sortSelectedFirst" in js
    assert "selectedIds = state.selectedChatIds" in js
    assert "selectedIds: state.editSelectedChatIds" in js
    assert "renderEditFolderPicker();" in js
    assert ".pagination" in css
    assert "[hidden]" in css


def test_miniapp_has_audit_tab_with_top_pagination() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    for element_id in [
        "audit-count",
        "audit-pagination",
        "audit-prev",
        "audit-next",
        "audit-page",
        "audit-list",
    ]:
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js

    assert 'data-tab="audit"' in html
    assert 'data-tab-panel="audit"' in html
    assert "auditPageSize: 20" in js
    assert 'api(`audit?page=${state.auditPage}&page_size=${state.auditPageSize}`)' in js
    assert "function renderAudit" in js
    assert "function renderAuditPagination" in js
    assert "function auditStatusLabel" in js
    assert "Успешно" in js
    assert "Ошибка" in js
    assert ".tab-bar" in css
    assert ".audit-list" in css
    assert ".audit-pagination" in css


def test_miniapp_datetime_inputs_are_constrained_on_mobile() -> None:
    html = read("index.html")
    css = read("styles.css")

    assert 'type="datetime-local"' in html
    assert 'input[type="datetime-local"]' in css
    assert "max-width: 100%" in css
    assert "-webkit-appearance: none" in css


def test_miniapp_spam_guard_is_visible_in_ui_and_payload() -> None:
    html = read("index.html")
    js = read("app.js")

    assert 'name="interval_minutes" type="number" min="20"' in html
    assert "Минимальный интервал повтора" in js
    assert "За частую отправку сообщений" in js
    assert "Я понимаю" in js
    assert "confirmSpamRiskIfNeeded" in js
    assert "spam_risk_acknowledged" in js


def test_miniapp_supports_rich_schedule_modes() -> None:
    html = read("index.html")
    js = read("app.js")

    for value in [
        "daily",
        "weekdays",
        "weekends",
        "every_other_day",
        "custom_weekdays",
    ]:
        assert f'value="{value}"' in html

    assert 'name="schedule_weekdays"' in html
    assert "schedule_weekdays: scheduleWeekdays" in js
    assert "weekdaySummary" in js
    assert "updateScheduleControls" in js


def test_miniapp_cache_bust_versions_match_for_css_and_js() -> None:
    html = read("index.html")
    versions = re.findall(r"[.?&]v=(\d{8}-\d+)", html)

    assert versions
    assert len(set(versions)) == 1
