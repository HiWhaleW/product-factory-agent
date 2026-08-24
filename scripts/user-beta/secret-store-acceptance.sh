#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/product-factory-user-secret.XXXXXX")"
credential_saved=false
cleanup() {
  if [[ "$credential_saved" == true && -f "$work_dir/cookies" ]]; then
    curl -sS -b "$work_dir/cookies" -X DELETE \
      "$web_url/api/control/api/v1/me/provider-credentials/model-api" >/dev/null 2>&1 || true
  fi
  rm -rf "$work_dir"
}
trap cleanup EXIT
web_url="http://$USER_BETA_WEB_HOST:$USER_BETA_WEB_PORT"
invite_code="$(user_beta_read_invite_code)"
test_key="test-only-user-beta-key-20260824"

curl -fsS -c "$work_dir/cookies" -o "$work_dir/login.json" \
  -H 'Content-Type: application/json' --data "{\"invite_code\":\"$invite_code\"}" \
  "$web_url/api/control/api/v1/auth/session"
curl -fsS -b "$work_dir/cookies" -o "$work_dir/before.json" \
  "$web_url/api/control/api/v1/me/provider-credentials/model-api"
grep -q '"configured":false' "$work_dir/before.json"

curl -fsS -b "$work_dir/cookies" -o "$work_dir/saved.json" \
  -X PUT -H 'Content-Type: application/json' \
  --data "{\"provider_name\":\"验收接口\",\"base_url\":\"https://models.example.com/v1\",\"model_name\":\"acceptance-model\",\"api_key\":\"$test_key\"}" \
  "$web_url/api/control/api/v1/me/provider-credentials/model-api"
grep -q '"configured":true' "$work_dir/saved.json"
credential_saved=true
if grep -q "$test_key" "$work_dir/saved.json"; then
  echo "API 响应泄露了 Key 原文。" >&2
  exit 1
fi

secret_files="$(find "$USER_BETA_RUNTIME/secrets" -type f -name '*.key' -print)"
if [[ "$(printf '%s\n' "$secret_files" | sed '/^$/d' | wc -l | tr -d ' ')" != "1" ]]; then
  echo "Secret Store 文件数量不符合验收预期。" >&2
  exit 1
fi
secret_file="$(printf '%s\n' "$secret_files" | sed -n '1p')"
if [[ "$(stat -f '%Lp' "$secret_file")" != "600" ]]; then
  echo "用户 Key 文件权限不是 0600。" >&2
  exit 1
fi

curl -fsS -b "$work_dir/cookies" -o "$work_dir/removed.json" \
  -X DELETE "$web_url/api/control/api/v1/me/provider-credentials/model-api"
grep -q '"configured":false' "$work_dir/removed.json"
credential_saved=false
if find "$USER_BETA_RUNTIME/secrets" -type f -name '*.key' -print | grep -q .; then
  echo "删除后 Secret Store 仍残留用户 Key 文件。" >&2
  exit 1
fi
echo "用户 Secret Store 验收通过：添加、脱敏响应、0600 权限和删除闭环均通过。"
