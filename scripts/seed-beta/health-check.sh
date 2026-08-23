#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
seed_beta_load_env
seed_beta_require_command curl

api_url="http://$SEED_BETA_API_HOST:$SEED_BETA_API_PORT"
web_url="http://$SEED_BETA_WEB_HOST:$SEED_BETA_WEB_PORT"
work_dir="$(mktemp -d "${TMPDIR:-/tmp}/product-factory-health.XXXXXX")"
trap 'rm -rf "$work_dir"' EXIT

curl -fsS "$api_url/health" > "$work_dir/health.json"
grep -q '"status":"ok"' "$work_dir/health.json"
grep -q '"app_env":"seed_beta"' "$work_dir/health.json"

protected_status="$(curl -sS -o "$work_dir/protected.json" -w '%{http_code}' "$api_url/api/v1/projects")"
if [[ "$protected_status" != "401" ]]; then
  echo "未登录访问受保护 API 应返回 401，实际为 $protected_status。" >&2
  exit 1
fi
grep -q 'AUTH_REQUIRED' "$work_dir/protected.json"

curl -fsS -D "$work_dir/web.headers" -o "$work_dir/web.html" "$web_url/"
grep -qi '^content-security-policy:' "$work_dir/web.headers"
grep -qi '^x-content-type-options: nosniff' "$work_dir/web.headers"
grep -qi '^x-frame-options: DENY' "$work_dir/web.headers"
grep -qi '^referrer-policy: no-referrer' "$work_dir/web.headers"
grep -q '造物工场' "$work_dir/web.html"

invite_code="$(tr -d '\n' < "$SEED_BETA_RUNTIME/invite-code.txt")"
login_status="$(
  curl -sS -c "$work_dir/cookies" -o "$work_dir/login.json" -w '%{http_code}' \
    -H 'Content-Type: application/json' \
    --data "{\"invite_code\":\"$invite_code\"}" \
    "$web_url/api/control/api/v1/auth/session"
)"
if [[ "$login_status" != "200" ]]; then
  echo "邀请码登录应返回 200，实际为 $login_status。" >&2
  exit 1
fi
grep -q '"authenticated":true' "$work_dir/login.json"
grep -q '^#HttpOnly_' "$work_dir/cookies"

authenticated_status="$(
  curl -sS -b "$work_dir/cookies" -o "$work_dir/projects.json" -w '%{http_code}' \
    "$web_url/api/control/api/v1/projects"
)"
if [[ "$authenticated_status" != "200" ]]; then
  echo "登录后访问项目 API 应返回 200，实际为 $authenticated_status。" >&2
  exit 1
fi

set +e
curl -sS --max-time 2 -b "$work_dir/cookies" \
  -D "$work_dir/sse.headers" -o "$work_dir/sse.body" \
  -H 'Accept: text/event-stream' -H 'Last-Event-ID: 999999' \
  "$web_url/api/control/api/v1/projects/$SEED_BETA_PROJECT_ID/events/stream" \
  2> "$work_dir/sse.stderr"
sse_exit=$?
set -e
if [[ "$sse_exit" != "0" && "$sse_exit" != "28" ]]; then
  echo "SSE 长连接检查失败，curl exit=$sse_exit。" >&2
  exit 1
fi
grep -qi '^content-type: text/event-stream' "$work_dir/sse.headers"
grep -qi '^x-event-stream-mode: ag-ui-live' "$work_dir/sse.headers"

seed_beta_python preflight > "$work_dir/state.json"
echo "健康检查通过："
echo "Web URL：$web_url"
echo "API URL：$api_url"
echo "数据库、Alembic head、G5/Context、强制认证、HttpOnly Session、SSE 和安全响应头均通过。"
