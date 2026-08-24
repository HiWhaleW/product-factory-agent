#!/usr/bin/env bash

set -euo pipefail

SEED_BETA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
SEED_BETA_RUNTIME="$SEED_BETA_ROOT/.runtime/seed-beta"
SEED_BETA_ENV_FILE="$SEED_BETA_RUNTIME/seed-beta.env"
SEED_BETA_PROJECT_ID="2a3c38e1-9704-4f83-a096-84cb5a5025e7"

seed_beta_load_env() {
  if [[ ! -f "$SEED_BETA_ROOT/.env" ]]; then
    echo "缺少 $SEED_BETA_ROOT/.env，无法加载数据库和运行路径配置。" >&2
    exit 1
  fi
  if [[ ! -f "$SEED_BETA_ENV_FILE" ]]; then
    echo "缺少内测配置，请先运行 scripts/seed-beta/configure.sh。" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1091
  source "$SEED_BETA_ROOT/.env"
  # shellcheck disable=SC1090
  source "$SEED_BETA_ENV_FILE"
  set +a
  export USER_SECRET_ROOT="$SEED_BETA_RUNTIME/secrets"
}

seed_beta_python() {
  env PYTHONPATH="$SEED_BETA_ROOT/apps/api" UV_CACHE_DIR="$SEED_BETA_ROOT/.uv-cache" \
    "$SEED_BETA_ROOT/.venv/bin/python" "$SEED_BETA_ROOT/scripts/seed-beta/ops.py" "$@"
}

seed_beta_read_invite_code() {
  local invite_file="$SEED_BETA_RUNTIME/invite-code.txt"
  local invite_code
  [[ -f "$invite_file" ]] || {
    echo "缺少内部验证环境邀请码文件。" >&2
    return 1
  }
  invite_code="$(sed -n 's/^邀请码：//p' "$invite_file" | head -n 1)"
  if [[ -z "$invite_code" ]]; then
    invite_code="$(tr -d '[:space:]' < "$invite_file")"
  fi
  [[ -n "$invite_code" ]] || {
    echo "内部验证环境邀请码为空。" >&2
    return 1
  }
  printf '%s' "$invite_code"
}

seed_beta_pid_running() {
  local pid_file="$1"
  local expected_marker="${2:-}"
  local expected_port="${3:-}"
  [[ -f "$pid_file" ]] || return 1
  local process_id
  process_id="$(tr -d '[:space:]' < "$pid_file")"
  [[ "$process_id" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$process_id" 2>/dev/null || return 1
  if [[ -n "$expected_marker" ]]; then
    local command_line
    command_line="$(ps -p "$process_id" -o command= 2>/dev/null || true)"
    [[ "$command_line" == *"$expected_marker"* ]] || return 1
  fi
  if [[ -n "$expected_port" ]]; then
    lsof -nP -a -p "$process_id" -iTCP:"$expected_port" -sTCP:LISTEN 2>/dev/null \
      | tail -n +2 | grep -q . || return 1
  fi
}

seed_beta_require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少必需命令：$1" >&2
    exit 1
  }
}
