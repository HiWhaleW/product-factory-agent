#!/usr/bin/env bash

set -euo pipefail

USER_BETA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
USER_BETA_RUNTIME="$USER_BETA_ROOT/.runtime/user-beta"
USER_BETA_ENV_FILE="$USER_BETA_RUNTIME/user-beta.env"

user_beta_load_env() {
  if [[ ! -f "$USER_BETA_ROOT/.env" ]]; then
    echo "缺少 $USER_BETA_ROOT/.env。" >&2
    exit 1
  fi
  if [[ ! -f "$USER_BETA_ENV_FILE" ]]; then
    echo "缺少用户环境配置，请先运行 scripts/user-beta/configure.sh。" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1091
  source "$USER_BETA_ROOT/.env"
  # shellcheck disable=SC1090
  source "$USER_BETA_ENV_FILE"
  set +a
  export USER_SECRET_ROOT="$USER_BETA_RUNTIME/secrets"
}

user_beta_python() {
  env PYTHONPATH="$USER_BETA_ROOT/apps/api" UV_CACHE_DIR="$USER_BETA_ROOT/.uv-cache" \
    "$USER_BETA_ROOT/.venv/bin/python" "$@"
}

user_beta_pid_running() {
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

user_beta_require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少必需命令：$1" >&2
    exit 1
  }
}
