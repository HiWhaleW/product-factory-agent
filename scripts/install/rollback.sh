#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env

current_tag="$(env_value PRODUCT_FACTORY_IMAGE_TAG)"
previous_tag="$(env_value PREVIOUS_IMAGE_TAG)"
[[ -n "${previous_tag}" ]] || die "没有可回滚的上一镜像标签。"
docker image inspect "product-factory-api:${previous_tag}" >/dev/null 2>&1 \
  || die "本机缺少 API 上一镜像：${previous_tag}"
docker image inspect "product-factory-web:${previous_tag}" >/dev/null 2>&1 \
  || die "本机缺少 Web 上一镜像：${previous_tag}"

replace_env_value PRODUCT_FACTORY_IMAGE_TAG "${previous_tag}"
replace_env_value PREVIOUS_IMAGE_TAG "${current_tag}"
compose up -d --no-build
"${INSTALL_SCRIPT_DIR}/health.sh" --wait
printf '代码镜像已回滚：%s → %s。数据库保持前向版本；如需数据回退，请先运行 restore-check，再显式 restore。\n' \
  "${current_tag}" "${previous_tag}"
