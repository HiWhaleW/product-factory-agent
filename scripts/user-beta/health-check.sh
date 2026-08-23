#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env
user_beta_require_command curl

api_url="http://$USER_BETA_API_HOST:$USER_BETA_API_PORT"
web_url="http://$USER_BETA_WEB_HOST:$USER_BETA_WEB_PORT"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/product-factory-user-health.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

curl -fsS "$api_url/health" > "$work_dir/health.json"
grep -q '"status":"ok"' "$work_dir/health.json"
grep -q '"app_env":"production"' "$work_dir/health.json"

protected_status="$(curl -sS -o "$work_dir/protected.json" -w '%{http_code}' "$api_url/api/v1/projects")"
[[ "$protected_status" == "401" ]]
grep -q 'AUTH_REQUIRED' "$work_dir/protected.json"

curl -fsS -D "$work_dir/web.headers" -o "$work_dir/web.html" "$web_url/"
grep -qi '^content-security-policy:' "$work_dir/web.headers"
grep -qi '^x-content-type-options: nosniff' "$work_dir/web.headers"
grep -qi '^x-frame-options: DENY' "$work_dir/web.headers"
grep -qi '^referrer-policy: no-referrer' "$work_dir/web.headers"

invite_code="$(tr -d '\n' < "$USER_BETA_RUNTIME/invite-code.txt")"
login_status="$(
  curl -sS -c "$work_dir/cookies" -o "$work_dir/login.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' --data "{\"invite_code\":\"$invite_code\"}" \
    "$web_url/api/control/api/v1/auth/session"
)"
[[ "$login_status" == "200" ]]
grep -q '"authenticated":true' "$work_dir/login.json"
grep -q '"role":"user"' "$work_dir/login.json"
grep -q '^#HttpOnly_' "$work_dir/cookies"

projects_status="$(
  curl -sS -b "$work_dir/cookies" -o "$work_dir/projects.json" -w '%{http_code}' \
    "$web_url/api/control/api/v1/projects"
)"
[[ "$projects_status" == "200" ]]
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" preflight > "$work_dir/state.json"
echo "用户环境健康检查通过："
echo "Web URL：$web_url"
echo "API URL：$api_url"
echo "独立数据库、强制认证、真实用户 Session 和安全响应头均通过。"
