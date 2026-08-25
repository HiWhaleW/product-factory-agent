#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_docker
require_install_env
compose config --quiet
compose up -d
"${INSTALL_SCRIPT_DIR}/health.sh" --wait
