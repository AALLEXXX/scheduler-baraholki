# Autopost Manager

Telegram-first autoposting manager:

- Telegram Bot opens the admin Mini App and sends alerts.
- FastAPI backend stores posts, targets, schedules, sessions, and jobs.
- Postgres is the source of truth.
- Scheduler creates publish jobs.
- Worker sends jobs through MTProto user sessions via Telethon.

`n8n` is intentionally not part of the MVP. It can be added later as an external integration that calls the backend API.

## Local bootstrap

```bash
cp .env.example .env
docker compose up --build
```

Open the Mini App through the Telegram bot in production. For local API checks:

```bash
curl http://localhost:8000/health
```

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest --cov=autopost_manager --cov-report=term-missing
```

The test suite uses SQLite under `/tmp` and mocks Telegram/Telethon calls, so it does not need
real Telegram credentials or a local Postgres instance.

## Session login

Each Telegram user account gets a separate Telethon session.

```bash
docker compose run --rm worker autopost-login-session "Main Account" "+10000000000"
```

The command creates or updates a session row and stores the session file under `TELEGRAM_SESSIONS_DIR`.

## Secrets

Never commit `.env`, BotFather tokens, `api_hash`, or `*.session` files.
