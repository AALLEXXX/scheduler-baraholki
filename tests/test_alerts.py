from __future__ import annotations

import asyncio
from types import SimpleNamespace

from autopost_manager.alerts import alert_text
from autopost_manager.config import get_settings


def test_alert_text_escapes_and_truncates_fields() -> None:
    text = alert_text(
        title="Broken <send>",
        status="failed",
        fields={"error": "<boom> " * 80, "user": 111},
    )

    assert "Broken &lt;send&gt;" in text
    assert "&lt;boom&gt;" in text
    assert "<boom>" not in text
    assert "…" in text
    assert "<b>user:</b> 111" in text


def test_default_alert_chat_is_configured() -> None:
    assert -5418121924 in get_settings().alert_ids


def test_send_alert_does_not_raise_on_delivery_setup_errors(monkeypatch) -> None:
    from autopost_manager import alerts

    monkeypatch.setattr(alerts, "get_settings", lambda: SimpleNamespace(app_env="prod", alert_ids=["not-an-int"]))

    asyncio.run(alerts.send_alert(title="Broken", fields={"error": "boom"}))
