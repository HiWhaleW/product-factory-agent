#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/product-factory-user-acceptance.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT
web_url="http://$USER_BETA_WEB_HOST:$USER_BETA_WEB_PORT"
invite_code="$(tr -d '\n' < "$USER_BETA_RUNTIME/invite-code.txt")"
curl -fsS -c "$work_dir/cookies" -o "$work_dir/login.json" \
  -H 'Content-Type: application/json' --data "{\"invite_code\":\"$invite_code\"}" \
  "$web_url/api/control/api/v1/auth/session"
curl -fsS -b "$work_dir/cookies" -o "$work_dir/projects.json" \
  "$web_url/api/control/api/v1/projects"
if [[ "$(tr -d '[:space:]' < "$work_dir/projects.json")" != "[]" ]]; then
  echo "新用户环境首次项目列表必须为空。" >&2
  exit 1
fi
if grep -q '销售复盘 Agent' "$work_dir/projects.json"; then
  echo "用户环境泄露了内部销售复盘项目。" >&2
  exit 1
fi
echo "用户环境首次登录验收通过：真实用户已记录，项目列表为空，内部项目未泄露。"
