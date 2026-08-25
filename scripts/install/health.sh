#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env
require_command curl

wait_mode=false
if [[ "${1:-}" == "--wait" ]]; then
  wait_mode=true
fi

web_url="http://$(env_value WEB_BIND_ADDRESS):$(env_value WEB_PORT)"
attempts=1
${wait_mode} && attempts=60

for ((attempt = 1; attempt <= attempts; attempt++)); do
  api_ok=false
  web_ok=false
  migration_ok=false
  if compose exec -T api python -c \
    "import json,urllib.request; body=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)); assert body['status']=='ok'" \
    >/dev/null 2>&1; then
    api_ok=true
  fi
  if curl -fsS --max-time 5 "${web_url}/" >/dev/null 2>&1; then
    web_ok=true
  fi
  if compose run --rm --no-deps migrate alembic -c apps/api/alembic.ini current 2>/dev/null \
    | grep -q '(head)'; then
    migration_ok=true
  fi
  if ${api_ok} && ${web_ok} && ${migration_ok}; then
    printf '健康检查通过：Web、API、PostgreSQL 与 Alembic head 正常。\n'
    exit 0
  fi
  if ! ${wait_mode}; then
    break
  fi
  sleep 3
done

compose ps >&2 || true
die "健康检查未通过。查看日志：docker compose --env-file .product-factory/install.env -f compose.yaml logs"
