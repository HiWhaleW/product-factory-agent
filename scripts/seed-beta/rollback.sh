#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

current_link="$SEED_BETA_RUNTIME/current"
previous_link="$SEED_BETA_RUNTIME/previous"
if [[ ! -L "$current_link" || ! -L "$previous_link" ]]; then
  echo "缺少 current 或 previous 发布包，无法执行应用回滚。" >&2
  exit 1
fi
current_target="$(readlink "$current_link")"
previous_target="$(readlink "$previous_link")"
if [[ ! -d "$current_target" || ! -d "$previous_target" ]]; then
  echo "发布包链接无效，拒绝回滚。" >&2
  exit 1
fi
case "$previous_target" in
  "$SEED_BETA_RUNTIME"/releases/*) ;;
  *) echo "previous 不在受控 releases 目录内，拒绝回滚。" >&2; exit 1 ;;
esac

"$SEED_BETA_ROOT/scripts/seed-beta/stop.sh"
ln -sfn "$previous_target" "$current_link"
ln -sfn "$current_target" "$previous_link"
"$SEED_BETA_ROOT/scripts/seed-beta/start.sh"

echo "应用已回滚到发布包：$(basename "$previous_target")"
