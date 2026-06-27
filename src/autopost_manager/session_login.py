from __future__ import annotations

import sys

from telethon import TelegramClient

from autopost_manager.cli.session_login import login_session as cli_login_session
from autopost_manager.cli.session_login import main as cli_main


async def login_session(owner_telegram_id: int, name: str, phone: str) -> None:
    await cli_login_session(owner_telegram_id, name, phone, telegram_client_class=TelegramClient)


def main() -> None:
    cli_main(sys.argv[1:])


if __name__ == "__main__":
    main()
