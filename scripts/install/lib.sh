#!/usr/bin/env bash
set -euo pipefail

INSTALL_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${INSTALL_SCRIPT_DIR}/../.." && pwd)"
STATE_DIR="${PROJECT_ROOT}/.product-factory"
INSTALL_ENV="${STATE_DIR}/install.env"
COMPOSE_FILE="${PROJECT_ROOT}/compose.yaml"

die() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

require_docker() {
  require_command docker
  docker compose version >/dev/null 2>&1 || die "需要 Docker Compose v2（docker compose）。"
  docker info >/dev/null 2>&1 || die "Docker 引擎未启动。"
}

require_install_env() {
  [[ -f "${INSTALL_ENV}" ]] || die "尚未安装。请先运行 scripts/install/install.sh。"
  [[ ! -L "${INSTALL_ENV}" ]] || die "安装配置不能是符号链接。"
}

compose() {
  docker compose --env-file "${INSTALL_ENV}" -f "${COMPOSE_FILE}" "$@"
}

env_value() {
  local key="$1"
  local value
  value="$(sed -n "s/^${key}=//p" "${INSTALL_ENV}" | tail -n 1)"
  [[ -n "${value}" ]] || die "安装配置缺少 ${key}。"
  printf '%s' "${value}"
}

replace_env_value() {
  local key="$1"
  local value="$2"
  local temporary="${INSTALL_ENV}.tmp.$$"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 { print key "=" value; replaced = 1; next }
    { print }
    END { if (!replaced) print key "=" value }
  ' "${INSTALL_ENV}" >"${temporary}"
  chmod 600 "${temporary}"
  mv "${temporary}" "${INSTALL_ENV}"
}

verify_backup() {
  local backup_dir="$1"
  [[ -d "${backup_dir}" && ! -L "${backup_dir}" ]] || die "备份目录不存在或不安全：${backup_dir}"
  [[ -f "${backup_dir}/database.dump" ]] || die "备份缺少 database.dump。"
  [[ -f "${backup_dir}/data.tar.gz" ]] || die "备份缺少 data.tar.gz。"
  [[ -f "${backup_dir}/install.env" ]] || die "备份缺少 install.env。"
  [[ -f "${backup_dir}/SHA256SUMS" ]] || die "备份缺少 SHA256SUMS。"
  (cd "${backup_dir}" && shasum -a 256 -c SHA256SUMS >/dev/null) \
    || die "备份完整性校验失败。"
}
