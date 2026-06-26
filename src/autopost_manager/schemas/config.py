from __future__ import annotations

from pydantic import BaseModel


class AppConfigOut(BaseModel):
    bot_username: str
    is_admin: bool = False


class UserSettingsOut(BaseModel):
    autopost_paused: bool = False
