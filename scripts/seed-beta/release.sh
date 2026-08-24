#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
seed_beta_load_env

seed_beta_python preflight

cd "$SEED_BETA_ROOT/apps/web"
env CI=true NEXT_TELEMETRY_DISABLED=1 PRODUCT_FACTORY_API_URL="$PRODUCT_FACTORY_API_URL" \
  ./node_modules/.bin/next build --webpack

release_id="$(date -u '+%Y%m%dT%H%M%SZ')"
release_dir="$SEED_BETA_RUNTIME/releases/$release_id"
if [[ -e "$release_dir" ]]; then
  release_id="${release_id}-$$"
  release_dir="$SEED_BETA_RUNTIME/releases/$release_id"
fi

staging_dir="${release_dir}.staging.$$"
cleanup_staging() {
  if [[ -d "$staging_dir" ]]; then
    rm -rf -- "$staging_dir"
  fi
}
trap cleanup_staging EXIT
"$SEED_BETA_ROOT/.venv/bin/python" \
  "$SEED_BETA_ROOT/scripts/release/build_release.py" package \
  --source-root "$SEED_BETA_ROOT" \
  --release-dir "$staging_dir" \
  --release-id "$release_id"
chmod -R u=rwX,go=rX "$staging_dir"
mv "$staging_dir" "$release_dir"
trap - EXIT

current_link="$SEED_BETA_RUNTIME/current"
previous_link="$SEED_BETA_RUNTIME/previous"
if [[ -L "$current_link" ]]; then
  current_target="$(readlink "$current_link")"
  if [[ -d "$current_target" ]]; then
    ln -sfn "$current_target" "$previous_link"
  fi
fi
ln -sfn "$release_dir" "$current_link"

echo "内测发布包已生成并切换为 current：$release_id"
