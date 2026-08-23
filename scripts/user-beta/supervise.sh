#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" preflight

current_link="$USER_BETA_RUNTIME/current"
if [[ ! -L "$current_link" || ! -d "$current_link" ]]; then
  echo "没有用户环境发布版本，请先运行 release.sh。" >&2
  exit 1
fi
release_dir="$(cd "$current_link" && pwd -P)"
mkdir -p "$USER_BETA_RUNTIME/logs"
rm -f "$USER_BETA_RUNTIME/api.pid" "$USER_BETA_RUNTIME/web.pid"

api_pid=""
web_pid=""
cleanup() {
  trap - EXIT INT TERM HUP
  if [[ -n "$web_pid" ]] && kill -0 "$web_pid" 2>/dev/null; then
    kill -TERM "$web_pid" 2>/dev/null || true
  fi
  if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null; then
    kill -TERM "$api_pid" 2>/dev/null || true
  fi
  wait "$web_pid" 2>/dev/null || true
  wait "$api_pid" 2>/dev/null || true
  rm -f "$USER_BETA_RUNTIME/api.pid" "$USER_BETA_RUNTIME/web.pid"
}
trap cleanup EXIT INT TERM HUP

cd "$USER_BETA_ROOT"
env PYTHONPATH="$release_dir/apps/api" UV_CACHE_DIR="$USER_BETA_ROOT/.uv-cache" \
  "$USER_BETA_ROOT/.venv/bin/uvicorn" app.main:app --app-dir "$release_dir/apps/api" \
  --host "$USER_BETA_API_HOST" --port "$USER_BETA_API_PORT" \
  > "$USER_BETA_RUNTIME/logs/api.log" 2>&1 &
api_pid=$!
printf '%s\n' "$api_pid" > "$USER_BETA_RUNTIME/api.pid"

cd "$release_dir/apps/web"
env NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
  PRODUCT_FACTORY_API_URL="$PRODUCT_FACTORY_API_URL" \
  "$release_dir/apps/web/node_modules/.bin/next" start \
  --hostname "$USER_BETA_WEB_HOST" --port "$USER_BETA_WEB_PORT" \
  > "$USER_BETA_RUNTIME/logs/web.log" 2>&1 &
web_pid=$!
printf '%s\n' "$web_pid" > "$USER_BETA_RUNTIME/web.pid"

while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 2
done

echo "用户环境子进程意外退出，监督进程将停止另一服务。" >&2
exit 1
