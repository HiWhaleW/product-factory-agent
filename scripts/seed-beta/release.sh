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

mkdir -p "$release_dir/apps/api" "$release_dir/apps/web"
cp -R "$SEED_BETA_ROOT/apps/api/app" "$release_dir/apps/api/app"
cp -R "$SEED_BETA_ROOT/apps/web/.next" "$release_dir/apps/web/.next"
cp -R "$SEED_BETA_ROOT/apps/web/public" "$release_dir/apps/web/public"
cp "$SEED_BETA_ROOT/apps/web/package.json" "$release_dir/apps/web/package.json"
ln -s "$SEED_BETA_ROOT/apps/web/node_modules" "$release_dir/apps/web/node_modules"
printf '%s\n' "$release_id" > "$release_dir/RELEASE_ID"
chmod -R u=rwX,go=rX "$release_dir"

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
