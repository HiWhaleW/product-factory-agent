#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
# shellcheck source=../release/lib.sh
source "$USER_BETA_ROOT/scripts/release/lib.sh"
user_beta_load_env
user_beta_require_command curl
user_beta_require_command node
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" preflight

current_link="$USER_BETA_RUNTIME/current"
if [[ ! -L "$current_link" || ! -d "$current_link" ]]; then
  echo "没有用户环境发布版本，请先运行 release.sh。" >&2
  exit 1
fi
if user_beta_pid_running "$USER_BETA_RUNTIME/api.pid" "uvicorn" "$USER_BETA_API_PORT" \
  || user_beta_pid_running "$USER_BETA_RUNTIME/web.pid" "" "$USER_BETA_WEB_PORT"; then
  echo "用户环境已在运行。" >&2
  exit 1
fi
release_dir="$(cd "$current_link" && pwd -P)"
if ! release_validate_runtime_layout "$release_dir"; then
  echo "current 发布包运行结构无效，拒绝启动。" >&2
  exit 1
fi
if [[ -f "$release_dir/RELEASE-MANIFEST.sha256" ]]; then
  "$USER_BETA_ROOT/.venv/bin/python" \
    "$USER_BETA_ROOT/scripts/release/build_release.py" verify \
    --release-dir "$release_dir"
fi
mkdir -p "$USER_BETA_RUNTIME/logs"
rm -f "$USER_BETA_RUNTIME/api.pid" "$USER_BETA_RUNTIME/web.pid"

cd "$USER_BETA_ROOT"
nohup env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$release_dir/apps/api" UV_CACHE_DIR="$USER_BETA_ROOT/.uv-cache" \
  "$USER_BETA_ROOT/.venv/bin/uvicorn" app.main:app --app-dir "$release_dir/apps/api" \
  --host "$USER_BETA_API_HOST" --port "$USER_BETA_API_PORT" \
  > "$USER_BETA_RUNTIME/logs/api.log" 2>&1 &
printf '%s\n' "$!" > "$USER_BETA_RUNTIME/api.pid"

if web_server="$(release_web_server_path "$release_dir")"; then
  cd "$(dirname "$web_server")"
  nohup env NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
    PRODUCT_FACTORY_API_URL="$PRODUCT_FACTORY_API_URL" \
    HOSTNAME="$USER_BETA_WEB_HOST" PORT="$USER_BETA_WEB_PORT" \
    "$(command -v node)" "$web_server" \
    > "$USER_BETA_RUNTIME/logs/web.log" 2>&1 &
else
  cd "$release_dir/apps/web"
  nohup env NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
    PRODUCT_FACTORY_API_URL="$PRODUCT_FACTORY_API_URL" \
    "$release_dir/apps/web/node_modules/.bin/next" start \
    --hostname "$USER_BETA_WEB_HOST" --port "$USER_BETA_WEB_PORT" \
    > "$USER_BETA_RUNTIME/logs/web.log" 2>&1 &
fi
printf '%s\n' "$!" > "$USER_BETA_RUNTIME/web.pid"

for _ in $(seq 1 60); do
  if curl -fsS "http://$USER_BETA_API_HOST:$USER_BETA_API_PORT/health" >/dev/null 2>&1 \
    && curl -fsS "http://$USER_BETA_WEB_HOST:$USER_BETA_WEB_PORT/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
"$USER_BETA_ROOT/scripts/user-beta/health-check.sh"
echo "独立用户环境已启动。"
