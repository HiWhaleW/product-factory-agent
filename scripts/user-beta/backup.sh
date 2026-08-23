#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
user_beta_load_env
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" backup
