#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env
compose stop web api db
printf '服务已停止；数据卷和备份均保留。\n'
