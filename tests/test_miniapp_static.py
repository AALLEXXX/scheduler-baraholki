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

    assert 'name="country_code"' in html
    assert 'name="phone_local"' in html
    assert 'pattern="[0-9\\s()+.-]*"' in html
    assert "phoneDigits" in js
    assert "formatPhoneLocal" in js
    assert "normalizePhoneInput" in js
    assert "isValidPhone" in js
    assert 'document.querySelector("input[name=phone_local]").addEventListener("input"' in js
    assert "validation.phoneInvalid" in js
    assert "loginPhoneFromForm" in js
    assert 'name="api_id"' not in html
    assert 'name="api_hash"' not in html
    assert "API ID" not in html
    assert "API Hash" not in html
    assert "Enter your phone number" in html
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
    assert 'id="draft-help-button"' in html
    assert 'id="draft-help-tooltip"' in html
    assert 'id="open-bot"' not in html
    assert 'id="refresh-drafts"' not in html
    assert 'id="sync-groups"' not in html
    assert "Открыть бота и создать пост" not in html
    assert "post will appear here as a draft" in html
    assert "Send the finished post to this bot" in html
    assert "draft-instruction" not in html
    assert "setDraftHelpVisible" in js
    assert "#draft-help-button" in js
    assert "#draft-help-tooltip" in js
    assert 'textarea name="body"' not in html
    assert "selectedDraftId" in js
    assert "visibleDrafts[0]?.id" not in js
    assert "toggleDraftSelection" in js
    assert "state.selectedDraftId === draftId ? null : draftId" in js
    assert 'api(`posts/${draftId}/schedule`' in js
    assert "validation.chooseDraft" in js
    assert "openTelegramBot" not in js
    assert "tg://resolve" not in js
    assert "#open-bot" not in js
    assert "#refresh-drafts" not in js
    assert "#sync-groups" not in js
    assert ".info-button" in css
    assert ".draft-help-popover" in css


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
    assert "notice.deleteMissingMessage" in js
    assert 'method: "DELETE"' in js
    assert "confirmDeletePost" in js
    assert ".danger-button" in css


def test_miniapp_queue_has_details_editing_and_precise_pause_controls() -> None:
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

    assert 't("form.when")' in js
    assert 't("groups.title")' in js
    assert "post-status-icon" in js
    assert "post-icon-button" in js
    assert 'aria-label="${t("post.action.edit")}"' in js
    assert 'aria-label="${t("delete.button")}"' in js
    assert "settings.pauseButton" in js
    assert "settings.resumeButton" in js
    assert "Pause sending" in js
    assert "togglePausePost" in js
    assert "openEditPost" in js
    assert 'method: "PATCH"' in js
    assert "/pause" in js
    assert "/resume" in js
    assert "edit.pastDate" in js
    assert 'class="queue-heading"' in html
    assert ".post-meta" in css
    assert ".post-icon-button" in css
    assert ".post-status-icon" in css
    assert ".post-title-row,\n  .audit-item-head" not in css
    assert ".post-item.scheduled" in css
    assert ".edit-page" in css
    assert ".edit-page-shell" in css
    assert ".edit-save-bar" in css
    assert ".back-button" in css
    assert 'id="edit-close" class="back-button secondary-button"' in html
    assert 'document.body.classList.add("editing-open")' in js


def test_miniapp_auto_syncs_groups_and_can_pause_or_revoke_account() -> None:
    html = read("index.html")
    js = read("app.js")

    assert 'data-tab="settings"' in html
    assert 'id="account-pause"' in html
    assert 'id="settings-pause"' in html
    assert 'id="revoke-session"' in html
    assert "account/pause" in js
    assert "account/resume" in js
    assert "account/revoke-session" in js
    assert "user-settings" in js
    assert "autoSyncGroups" in js
    assert "groupsSyncedOnInit" in js
    assert "syncGroups({ silent: true })" in js


def test_miniapp_defaults_to_english_and_can_switch_to_russian() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    assert '<html lang="en">' in html
    assert "<title>Baraholki</title>" in html
    assert 'id="language-select"' in html
    assert '<option value="en">English</option>' in html
    assert '<option value="ru">Русский</option>' in html
    assert 'class="settings-section-label"' in html
    assert 'class="settings-control"' in html
    assert 'data-i18n="settings.languageTitle"' in html
    assert 'data-i18n-placeholder="groups.search"' in html
    assert 'data-i18n-aria-label="action.refresh"' in html
    assert 'const languageStorageKey = "autopost-manager-language";' in js
    assert 'const supportedLanguages = ["en", "ru"];' in js
    assert 'language: localStorage.getItem(languageStorageKey) || "en"' in js
    assert "function applyTranslations" in js
    assert "function setLanguage" in js
    assert 'document.querySelector("#language-select").addEventListener("change"' in js
    assert '"settings.pauseTitle": "Autoposting"' in js
    assert '"settings.pauseTitle": "Автопостинг"' in js
    assert '"settings.pauseButton": "Pause sending"' in js
    assert '"settings.pauseButton": "Остановить отправки"' in js
    assert 'data-i18n="settings.limits"' in html
    assert 'class="settings-limits-grid"' in html
    assert 'data-i18n="limits.targetsValue">15 max' in html
    assert '"limits.targetsValue": "до 15"' in js
    assert '"limits.accountIntervalValue": "30 сек"' in js
    assert '"limits.queueValue": "300 задач"' in js
    assert ".settings-section-label" in css
    assert ".settings-control" in css
    assert ".settings-limits-grid" in css
    assert ".settings-limit" in css
    assert ".compact-select" in css


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
    assert "flex-wrap: wrap" in css
    assert ".folder-list" in css
    assert "function renderGroupPicker()" in js
    assert "selectedChatIds" in js
    assert "sortSelectedFirst" in js
    assert "selectedIds = state.selectedChatIds" in js
    assert "selectedIds: state.editSelectedChatIds" in js
    assert "renderEditFolderPicker();" in js
    assert ".pagination" in css
    assert "[hidden]" in css
    assert ".group-chip span" in css
    assert "text-overflow: ellipsis" in css
    assert "-webkit-line-clamp: 2" in css
    assert "overflow-wrap: anywhere" in css
    assert ".chip-grid" in css
    assert "overflow: hidden" in css


def test_miniapp_mobile_layout_keeps_status_and_form_inside_viewport() -> None:
    css = read("styles.css")

    assert "body" in css
    assert "overflow-x: hidden" in css
    assert ".status-panel {\n  display: grid;" in css
    assert ".status-panel {\n    grid-template-columns: minmax(0, 1fr);" in css
    assert "#account-subtitle" in css
    assert "overflow-wrap: anywhere" in css
    assert ".panel {\n  padding: 16px;\n  overflow: hidden;" in css


def test_miniapp_typography_avoids_heavy_font_weights() -> None:
    css = read("styles.css")

    heavy_weights = re.findall(r"font-weight:\s*(?:[78]\d\d|9\d\d)", css)

    assert heavy_weights == []


def test_miniapp_warns_when_selecting_more_than_fifteen_chats() -> None:
    js = read("app.js")

    assert "riskyChatSelectionLimit = 15" in js
    assert "showLargeChatSelectionWarning" in js
    assert "warnIfLargeChatSelection(previousCount, state.selectedChatIds.size)" in js
    assert "warnIfLargeChatSelection(previousCount, state.editSelectedChatIds.size)" in js
    assert "spam.largeSelection" in js
    assert "Continue at your own risk" in js


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
        "audit-message-modal",
        "audit-message-close",
        "audit-message-text",
        "audit-message-link",
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
    assert "audit.status.done" in js
    assert "audit.status.failed" in js
    assert "audit.viewMessage" in js
    assert "function loadAuditMessage" in js
    assert "function showAuditMessage" in js
    assert 'api(`audit/${item.id}/message`)' in js
    assert "item.message_link" in js
    assert "audit.messageId" not in js
    assert ".tab-bar" in css
    assert ".audit-list" in css
    assert ".audit-pagination" in css
    assert ".audit-actions" in css
    assert ".audit-message-text" in css


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
    assert "spam.minInterval" in js
    assert "spam.riskMessage" in js
    assert "spam.understand" in js
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


def test_miniapp_preserves_folder_picker_and_falls_back_when_folder_api_fails() -> None:
    js = read("app.js")

    assert 'api("folders").catch(() => state.folders)' in js
    assert "function folderItems" in js
    assert 'title: t("folder.all")' in js
    assert "renderFolderPicker()" in js
    assert "renderEditFolderPicker()" in js


def test_miniapp_has_admin_tabs_for_users_and_stats() -> None:
    html = read("index.html")
    js = read("app.js")
    css = read("styles.css")

    for element_id in [
        "admin-tab-button",
        "admin-tabs",
        "admin-users",
        "admin-stats",
        "admin-user-search",
        "admin-user-list",
        "admin-users-pagination",
        "admin-stats-grid",
    ]:
        assert f'id="{element_id}"' in html
        assert f"#{element_id}" in js

    assert 'data-tab="admin"' in html
    assert 'class="header-actions"' in html
    assert 'class="admin-shortcut"' in html
    assert 'data-admin-tab="users"' in html
    assert 'data-admin-tab="stats"' in html
    assert "isAdmin()" in js
    assert 'document.querySelectorAll("[data-tab]")' in js
    assert 'api(`admin/users?page=${state.adminUsers.page}' in js
    assert 'api("admin/stats")' in js
    assert 'api(`admin/users/${telegramUserId}`' in js
    assert "daily_send_limit" in js
    assert "admin.ban" in js
    assert "admin.pause" in js
    assert ".admin-list" in css
    assert ".admin-stats-grid" in css
    assert ".admin-stat-hero" in css
    assert ".stat-ring" in css


def test_miniapp_cache_bust_versions_match_for_css_and_js() -> None:
    html = read("index.html")
    versions = re.findall(r"[.?&]v=(\d{8}-\d+)", html)

    assert versions
    assert len(set(versions)) == 1
