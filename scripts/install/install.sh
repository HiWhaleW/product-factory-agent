#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

require_docker
require_command openssl
require_command curl

umask 077
mkdir -p "${STATE_DIR}/backups" "${STATE_DIR}/restore-check"
chmod 700 "${STATE_DIR}" "${STATE_DIR}/backups" "${STATE_DIR}/restore-check"

if [[ ! -f "${INSTALL_ENV}" ]]; then
  install_id="$(date -u +%Y%m%dT%H%M%SZ)"
  db_password="$(openssl rand -hex 24)"
  session_secret="$(openssl rand -hex 48)"
  compose_project_name="${COMPOSE_PROJECT_NAME:-product-factory-local}"
  web_bind_address="${WEB_BIND_ADDRESS:-127.0.0.1}"
  web_port="${WEB_PORT:-3400}"
  app_env="${APP_ENV:-local}"
  [[ "${compose_project_name}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] \
    || die "COMPOSE_PROJECT_NAME 格式无效。"
  [[ "${web_bind_address}" == "127.0.0.1" ]] \
    || die "首次安装只允许 WEB_BIND_ADDRESS=127.0.0.1。"
  [[ "${web_port}" =~ ^[0-9]+$ && "${web_port}" -ge 1 && "${web_port}" -le 65535 ]] \
    || die "WEB_PORT 必须是 1-65535 的整数。"
  [[ "${app_env}" == "local" || "${app_env}" == "production" ]] \
    || die "APP_ENV 只允许 local 或 production。"
  {
    printf 'COMPOSE_PROJECT_NAME=%s\n' "${compose_project_name}"
    printf 'PRODUCT_FACTORY_IMAGE_TAG=local-%s\n' "${install_id}"
    printf 'PREVIOUS_IMAGE_TAG=\n'
    printf 'WEB_BIND_ADDRESS=%s\n' "${web_bind_address}"
    printf 'WEB_PORT=%s\n' "${web_port}"
    printf 'APP_ENV=%s\n' "${app_env}"
    printf 'POSTGRES_DB=product_factory\n'
    printf 'POSTGRES_USER=product_factory\n'
    printf 'POSTGRES_PASSWORD=%s\n' "${db_password}"
    printf 'SESSION_SECRET=%s\n' "${session_secret}"
  } >"${INSTALL_ENV}"
  chmod 600 "${INSTALL_ENV}"
  printf '已生成本机专用安装配置（权限 0600）。\n'
else
  printf '复用现有安装配置，不覆盖数据库密码或 Session Secret。\n'
fi

compose config --quiet
compose build --pull api web
compose up -d
"${INSTALL_SCRIPT_DIR}/health.sh" --wait

printf '\n安装完成： http://%s:%s\n' "$(env_value WEB_BIND_ADDRESS)" "$(env_value WEB_PORT)"
printf '首次打开后创建本地账户。模型和搜索 API 均保持空态。\n'
printf 'Builder 默认禁用；本安装未挂载宿主机或 Docker Socket。\n'
