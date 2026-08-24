#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

rotate=false
if [[ "${1:-}" == "--rotate" ]]; then
  rotate=true
fi

mkdir -p "$SEED_BETA_RUNTIME/logs" "$SEED_BETA_RUNTIME/backups" "$SEED_BETA_RUNTIME/releases"
chmod 700 "$SEED_BETA_RUNTIME"

if [[ -f "$SEED_BETA_ENV_FILE" && "$rotate" != true ]]; then
  echo "内测凭据和端口配置已存在；如需轮换，请使用 --rotate。"
  exit 0
fi

seed_beta_require_command openssl
seed_beta_require_command shasum

umask 077
invite_code="$(openssl rand -hex 16)"
invite_hash="$(printf '%s' "$invite_code" | shasum -a 256 | awk '{print $1}')"
session_secret="$(openssl rand -hex 48)"
env_tmp="$SEED_BETA_RUNTIME/seed-beta.env.tmp"
invite_tmp="$SEED_BETA_RUNTIME/invite-code.txt.tmp"

{
  printf 'APP_ENV=seed_beta\n'
  printf 'AUTH_ENFORCED=true\n'
  printf 'INVITE_CODE_HASH=%s\n' "$invite_hash"
  printf 'SESSION_SECRET=%s\n' "$session_secret"
  printf 'SESSION_TTL_SECONDS=28800\n'
  printf 'SEED_BETA_API_HOST=127.0.0.1\n'
  printf 'SEED_BETA_API_PORT=8200\n'
  printf 'SEED_BETA_WEB_HOST=127.0.0.1\n'
  printf 'SEED_BETA_WEB_PORT=3200\n'
  printf 'PRODUCT_FACTORY_API_URL=http://127.0.0.1:8200\n'
  printf 'USER_SECRET_ROOT=%s/secrets\n' "$SEED_BETA_RUNTIME"
} > "$env_tmp"
{
  printf '内部验证环境：http://127.0.0.1:3200/\n'
  printf '邀请码：%s\n' "$invite_code"
} > "$invite_tmp"
chmod 600 "$env_tmp" "$invite_tmp"
mv -f "$env_tmp" "$SEED_BETA_ENV_FILE"
mv -f "$invite_tmp" "$SEED_BETA_RUNTIME/invite-code.txt"

echo "内测配置已生成，权限为 600；邀请码只保存在 .runtime/seed-beta/invite-code.txt。"
echo "未修改项目根目录 .env，也未在终端输出凭据。"
