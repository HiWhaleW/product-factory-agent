#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
# shellcheck source=../release/lib.sh
source "$USER_BETA_ROOT/scripts/release/lib.sh"
user_beta_load_env
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" preflight

internal_current="$USER_BETA_ROOT/.runtime/seed-beta/current"
if [[ ! -L "$internal_current" || ! -d "$internal_current" ]]; then
  echo "内部验证环境没有可发布的 current 版本。" >&2
  exit 1
fi
if ! release_dir="$(release_resolve_controlled_dir \
  "$internal_current" "$USER_BETA_ROOT/.runtime/seed-beta/releases")"; then
  echo "内部 current 不在受控发布目录内。" >&2
  exit 1
fi
"$USER_BETA_ROOT/.venv/bin/python" \
  "$USER_BETA_ROOT/scripts/release/build_release.py" verify \
  --release-dir "$release_dir"
current_link="$USER_BETA_RUNTIME/current"
previous_link="$USER_BETA_RUNTIME/previous"
if [[ -L "$current_link" ]]; then
  current_target="$(readlink "$current_link")"
  if [[ -d "$current_target" ]]; then
    ln -sfn "$current_target" "$previous_link"
  fi
fi
ln -sfn "$release_dir" "$current_link"
echo "用户环境已绑定内部验收通过的同一发布版本：$(tr -d '\n' < "$release_dir/RELEASE_ID")"
