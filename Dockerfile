FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY src ./src
COPY miniapp ./miniapp
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir . \
    && mkdir -p /data \
    && chown -R app:app /app /data

USER app

CMD ["autopost-api"]
