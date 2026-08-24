#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
# shellcheck source=../release/lib.sh
source "$SEED_BETA_ROOT/scripts/release/lib.sh"
seed_beta_load_env
seed_beta_require_command node

current_link="$SEED_BETA_RUNTIME/current"
if [[ ! -L "$current_link" || ! -d "$current_link" ]]; then
  echo "没有 current 内测发布包，请先运行 scripts/seed-beta/release.sh。" >&2
  exit 1
fi
release_dir="$(cd "$current_link" && pwd -P)"
if ! release_validate_runtime_layout "$release_dir"; then
  echo "current 发布包运行结构无效，拒绝启动。" >&2
  exit 1
fi
if [[ -f "$release_dir/RELEASE-MANIFEST.sha256" ]]; then
  "$SEED_BETA_ROOT/.venv/bin/python" \
    "$SEED_BETA_ROOT/scripts/release/build_release.py" verify \
    --release-dir "$release_dir"
fi
mkdir -p "$SEED_BETA_RUNTIME/logs"
rm -f "$SEED_BETA_RUNTIME/api.pid" "$SEED_BETA_RUNTIME/web.pid"

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
  rm -f "$SEED_BETA_RUNTIME/api.pid" "$SEED_BETA_RUNTIME/web.pid"
}
trap cleanup EXIT INT TERM HUP

cd "$SEED_BETA_ROOT"
env \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$release_dir/apps/api" \
  UV_CACHE_DIR="$SEED_BETA_ROOT/.uv-cache" \
  "$SEED_BETA_ROOT/.venv/bin/uvicorn" app.main:app \
  --app-dir "$release_dir/apps/api" \
  --host "$SEED_BETA_API_HOST" \
  --port "$SEED_BETA_API_PORT" \
  > "$SEED_BETA_RUNTIME/logs/api.log" 2>&1 &
api_pid=$!
printf '%s\n' "$api_pid" > "$SEED_BETA_RUNTIME/api.pid"

if web_server="$(release_web_server_path "$release_dir")"; then
  cd "$(dirname "$web_server")"
  env \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PRODUCT_FACTORY_API_URL="$PRODUCT_FACTORY_API_URL" \
    HOSTNAME="$SEED_BETA_WEB_HOST" \
    PORT="$SEED_BETA_WEB_PORT" \
    "$(command -v node)" "$web_server" \
    > "$SEED_BETA_RUNTIME/logs/web.log" 2>&1 &
else
  cd "$release_dir/apps/web"
  env \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PRODUCT_FACTORY_API_URL="$PRODUCT_FACTORY_API_URL" \
    "$release_dir/apps/web/node_modules/.bin/next" start \
    --hostname "$SEED_BETA_WEB_HOST" \
    --port "$SEED_BETA_WEB_PORT" \
    > "$SEED_BETA_RUNTIME/logs/web.log" 2>&1 &
fi
web_pid=$!
printf '%s\n' "$web_pid" > "$SEED_BETA_RUNTIME/web.pid"

while kill -0 "$api_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 2
done

echo "内部环境子进程意外退出，监督进程将停止另一服务。" >&2
exit 1
