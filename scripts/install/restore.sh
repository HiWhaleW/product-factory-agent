#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env
require_command shasum

[[ "${1:-}" == "--confirm" && -n "${2:-}" ]] \
  || die "恢复会覆盖当前安装。用法：scripts/install/restore.sh --confirm <backup-id>"
backup_id="$2"
[[ "${backup_id}" =~ ^[0-9A-Za-z._-]+$ ]] || die "备份 ID 格式无效。"
backup_dir="${STATE_DIR}/backups/${backup_id}"
verify_backup "${backup_dir}"

compose stop web api >/dev/null 2>&1 || true
compose up -d --wait db
compose run --rm --no-deps init-storage
compose exec -T db sh -ec \
  'dropdb --force -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
compose run --rm --no-deps migrate sh -ec \
  'find /data/artifacts /data/workspaces /data/user-secrets /data/logs -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +'
compose run --rm --no-deps -T migrate tar -C /data -xzf - <"${backup_dir}/data.tar.gz"
compose exec -T db sh -ec \
  'pg_restore --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  <"${backup_dir}/database.dump"
compose run --rm migrate alembic -c apps/api/alembic.ini upgrade head
compose up -d
"${INSTALL_SCRIPT_DIR}/health.sh" --wait
printf '已从备份 %s 恢复当前安装。恢复前的当前数据已被覆盖。\n' "${backup_id}"
