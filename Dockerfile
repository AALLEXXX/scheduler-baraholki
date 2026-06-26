FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY src ./src
COPY miniapp ./miniapp
COPY alembic.ini ./
COPY alembic ./alembic

RUN uv pip install --no-cache . \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app

CMD ["autopost-api"]
