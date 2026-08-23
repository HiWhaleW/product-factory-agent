#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
seed_beta_load_env

stop_process() {
  local label="$1"
  local pid_file="$2"
  local expected_marker="$3"
  local expected_port="$4"
  if ! seed_beta_pid_running "$pid_file" "$expected_marker" "$expected_port"; then
    rm -f "$pid_file"
    return
  fi
  local process_id
  process_id="$(tr -d '[:space:]' < "$pid_file")"
  kill -TERM "$process_id"
  for _ in $(seq 1 20); do
    if ! kill -0 "$process_id" 2>/dev/null; then
      rm -f "$pid_file"
      echo "$label 已停止。"
      return
    fi
    sleep 0.25
  done
  echo "$label 未在宽限期内停止，保留进程并退出。" >&2
  exit 1
}

stop_process "Web" "$SEED_BETA_RUNTIME/web.pid" "next" "$SEED_BETA_WEB_PORT"
stop_process "API" "$SEED_BETA_RUNTIME/api.pid" "uvicorn" "$SEED_BETA_API_PORT"
