#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env
user_beta_require_command launchctl

set +e
launchctl remove com.productfactory.user-beta >/dev/null 2>&1
set -e
for _ in $(seq 1 20); do
  if ! lsof -nP -iTCP:"$USER_BETA_WEB_PORT" -sTCP:LISTEN >/dev/null 2>&1 \
    && ! lsof -nP -iTCP:"$USER_BETA_API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    rm -f "$USER_BETA_RUNTIME/api.pid" "$USER_BETA_RUNTIME/web.pid"
    echo "独立用户环境监督任务已停止。"
    exit 0
  fi
  sleep 0.25
done

"$USER_BETA_ROOT/scripts/user-beta/stop.sh"
