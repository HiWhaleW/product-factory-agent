#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env
require_command shasum

backup_id="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "${backup_id}" =~ ^[0-9A-Za-z._-]+$ ]] || die "备份 ID 只能包含字母、数字、点、下划线和连字符。"
backup_root="${STATE_DIR}/backups"
backup_dir="${backup_root}/${backup_id}"
[[ ! -e "${backup_dir}" ]] || die "备份已存在：${backup_id}"
umask 077
mkdir -p "${backup_dir}"
chmod 700 "${backup_dir}"

restart_required=false
cleanup() {
  if ${restart_required}; then
    compose start api web >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

compose stop web api >/dev/null
restart_required=true
compose exec -T db sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  >"${backup_dir}/database.dump"
compose run --rm --no-deps -T migrate tar -C /data -czf - artifacts workspaces user-secrets logs \
  >"${backup_dir}/data.tar.gz"
cp "${INSTALL_ENV}" "${backup_dir}/install.env"
chmod 600 "${backup_dir}/database.dump" "${backup_dir}/data.tar.gz" "${backup_dir}/install.env"
(
  cd "${backup_dir}"
  shasum -a 256 database.dump data.tar.gz install.env >SHA256SUMS
)
chmod 600 "${backup_dir}/SHA256SUMS"

compose start api web >/dev/null
restart_required=false
"${INSTALL_SCRIPT_DIR}/health.sh" --wait
printf '备份完成：%s\n' "${backup_dir}"
printf '备份包含用户数据与秘密，目录权限为 0700；请按敏感数据保管。\n'
