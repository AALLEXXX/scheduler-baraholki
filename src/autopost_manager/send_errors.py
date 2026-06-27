from __future__ import annotations

from dataclasses import dataclass

from telethon.errors import FloodWaitError


@dataclass(frozen=True, slots=True)
class SendErrorInfo:
    message: str
    limited: bool = False
    terminal: bool = False
    needs_login: bool = False


def classify_send_error_info(exc: Exception) -> SendErrorInfo:
    if isinstance(exc, FloodWaitError):
        return SendErrorInfo(message=f"FloodWait: wait {exc.seconds} seconds", limited=True)
    error_name = exc.__class__.__name__
    lowered = f"{error_name} {exc}".lower()
    if "needs login" in lowered or "unauthorized" in lowered:
        return SendErrorInfo(
            message=f"{error_name}: {exc}",
            terminal=True,
            needs_login=True,
        )
    if (
        "writeforbidden" in lowered
        or "userbannedinchannel" in lowered
        or "chatadminrequired" in lowered
        or "chatwriteforbidden" in lowered
        or "not enough rights" in lowered
        or "can't write" in lowered
        or "cannot write" in lowered
    ):
        return SendErrorInfo(
            message=(
                "Chat write forbidden: user is banned or not allowed to post "
                f"in this chat ({error_name}: {exc})"
            ),
            terminal=True,
        )
    return SendErrorInfo(message=f"{error_name}: {exc}")


def classify_send_error(exc: Exception) -> str:
    return classify_send_error_info(exc).message
