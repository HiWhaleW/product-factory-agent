# syntax=docker/dockerfile:1.7
FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 10001 productfactory \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin productfactory \
    && python -m pip install --no-cache-dir uv==0.12.1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api ./apps/api
COPY 产品工厂Agent/spec/prompts ./产品工厂Agent/spec/prompts
COPY deploy/api-logging.ini deploy/codex-disabled ./deploy/

RUN install -m 0755 deploy/codex-disabled /usr/local/bin/codex-disabled \
    && mkdir -p /data/artifacts /data/workspaces /data/user-secrets /data/logs \
    && chown -R 10001:10001 /app /data

USER 10001:10001
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/deploy/api-logging.ini"]
