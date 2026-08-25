#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env

if [[ "${1:-}" == "--purge-data" ]]; then
  [[ "${2:-}" == "--confirm" ]] \
    || die "永久删除当前安装数据卷需要：scripts/install/uninstall.sh --purge-data --confirm"
  compose down -v --remove-orphans
  rm -f "${INSTALL_ENV}"
  printf '容器、网络、当前安装数据卷和安装配置已删除。\n'
  printf '镜像与 .product-factory/backups 下的备份仍保留，可用于恢复。\n'
else
  compose down --remove-orphans
  printf '容器和网络已删除；数据卷、安装配置、镜像与备份均保留。\n'
fi
