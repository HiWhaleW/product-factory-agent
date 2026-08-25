#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env
require_command curl
require_command python3
require_command shasum

backup_id="${1:-}"
[[ -n "${backup_id}" && "${backup_id}" =~ ^[0-9A-Za-z._-]+$ ]] \
  || die "用法：scripts/install/restore-check.sh <backup-id>"
backup_dir="${STATE_DIR}/backups/${backup_id}"
verify_backup "${backup_dir}"

check_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
check_dir="${STATE_DIR}/restore-check/${check_id}"
check_env="${check_dir}/restore.env"
mkdir -p "${check_dir}"
chmod 700 "${check_dir}"
port="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"

while IFS= read -r line; do
  case "${line}" in
    COMPOSE_PROJECT_NAME=*|WEB_PORT=*) ;;
    *) printf '%s\n' "${line}" ;;
  esac
done <"${backup_dir}/install.env" >"${check_env}"
printf 'COMPOSE_PROJECT_NAME=product-factory-restore-%s\n' "${check_id}" >>"${check_env}"
printf 'WEB_PORT=%s\n' "${port}" >>"${check_env}"
chmod 600 "${check_env}"

restore_compose() {
  docker compose --env-file "${check_env}" -f "${COMPOSE_FILE}" "$@"
}

cleanup() {
  restore_compose down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "${check_env}"
}
trap cleanup EXIT

restore_compose up -d --wait db
restore_compose run --rm --no-deps init-storage
restore_compose exec -T db sh -ec \
  'pg_restore --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  <"${backup_dir}/database.dump"
restore_compose run --rm --no-deps -T migrate tar -C /data -xzf - \
  <"${backup_dir}/data.tar.gz"
restore_compose run --rm migrate alembic -c apps/api/alembic.ini upgrade head
restore_compose up -d

for _ in {1..60}; do
  if curl -fsS --max-time 5 "http://127.0.0.1:${port}/" >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
curl -fsS --max-time 5 "http://127.0.0.1:${port}/" >/dev/null
counts="$(restore_compose exec -T db sh -ec \
  'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select (select count(*) from users)::text || chr(9) || (select count(*) from projects)::text"')"
printf 'restore-check=passed\nbackup_id=%s\nuser_project_counts=%s\n' \
  "${backup_id}" "${counts}" >"${check_dir}/result.txt"
chmod 600 "${check_dir}/result.txt"
printf '隔离恢复检查通过；未改动当前安装。证据：%s\n' "${check_dir}/result.txt"
