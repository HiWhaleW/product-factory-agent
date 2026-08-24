#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
seed_beta_load_env

cd "$SEED_BETA_ROOT"
env PYTHONPATH="$SEED_BETA_ROOT/apps/api" UV_CACHE_DIR="$SEED_BETA_ROOT/.uv-cache" \
  "$SEED_BETA_ROOT/.venv/bin/alembic" -c "$SEED_BETA_ROOT/apps/api/alembic.ini" upgrade head
