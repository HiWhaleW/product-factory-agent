#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env

new_tag="${1:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
[[ "${new_tag}" =~ ^[0-9A-Za-z._-]+$ ]] || die "镜像标签格式无效。"
current_tag="$(env_value PRODUCT_FACTORY_IMAGE_TAG)"
[[ "${new_tag}" != "${current_tag}" ]] || die "新标签必须与当前标签不同。"

backup_id="pre-upgrade-$(date -u +%Y%m%dT%H%M%SZ)"
"${INSTALL_SCRIPT_DIR}/backup.sh" "${backup_id}"
replace_env_value PREVIOUS_IMAGE_TAG "${current_tag}"
replace_env_value PRODUCT_FACTORY_IMAGE_TAG "${new_tag}"

if ! compose build --pull api web || ! compose up -d || ! "${INSTALL_SCRIPT_DIR}/health.sh" --wait; then
  replace_env_value PRODUCT_FACTORY_IMAGE_TAG "${current_tag}"
  replace_env_value PREVIOUS_IMAGE_TAG "${new_tag}"
  compose up -d --no-build || true
  die "升级失败，已尝试切回原镜像。数据库备份：${backup_id}"
fi
printf '升级完成：%s → %s；升级前备份：%s\n' "${current_tag}" "${new_tag}" "${backup_id}"
