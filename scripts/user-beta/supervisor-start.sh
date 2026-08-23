#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env
user_beta_require_command launchctl
user_beta_require_command node
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" preflight

label="com.productfactory.user-beta"
set +e
launchctl remove "$label" >/dev/null 2>&1
set -e
"$USER_BETA_ROOT/scripts/user-beta/stop.sh" >/dev/null 2>&1 || true

node_dir="$(dirname "$(command -v node)")"
launchctl submit -l "$label" -- /usr/bin/env \
  "PATH=$node_dir:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  /bin/bash "$USER_BETA_ROOT/scripts/user-beta/supervise.sh"

for _ in $(seq 1 60); do
  if curl -fsS "http://$USER_BETA_API_HOST:$USER_BETA_API_PORT/health" >/dev/null 2>&1 \
    && curl -fsS "http://$USER_BETA_WEB_HOST:$USER_BETA_WEB_PORT/" >/dev/null 2>&1; then
    "$USER_BETA_ROOT/scripts/user-beta/health-check.sh"
    echo "独立用户环境已由本机监督任务启动。"
    exit 0
  fi
  sleep 1
done

echo "独立用户环境监督启动超时。" >&2
exit 1
