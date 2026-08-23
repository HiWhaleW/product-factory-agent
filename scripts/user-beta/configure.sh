#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
mkdir -p "$USER_BETA_RUNTIME/logs" "$USER_BETA_RUNTIME/backups" \
  "$USER_BETA_RUNTIME/artifacts" "$USER_BETA_RUNTIME/workspaces"
chmod 700 "$USER_BETA_RUNTIME"

cd "$USER_BETA_ROOT"
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/configure.py"
user_beta_load_env
env PYTHONPATH="$USER_BETA_ROOT/apps/api" UV_CACHE_DIR="$USER_BETA_ROOT/.uv-cache" \
  "$USER_BETA_ROOT/.venv/bin/alembic" -c "$USER_BETA_ROOT/apps/api/alembic.ini" upgrade head
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/provision_invite.py"
echo "独立用户环境已配置；邀请码只保存在 .runtime/user-beta/invite-code.txt。"
