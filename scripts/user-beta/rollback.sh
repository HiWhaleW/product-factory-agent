#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"

current_link="$USER_BETA_RUNTIME/current"
previous_link="$USER_BETA_RUNTIME/previous"
controlled_releases="$USER_BETA_ROOT/.runtime/seed-beta/releases"

if [[ ! -L "$current_link" || ! -L "$previous_link" ]]; then
  echo "用户环境尚无上一版安全版本，拒绝回滚；请先完成下一版内部验收并发布。" >&2
  exit 1
fi

current_target="$(readlink "$current_link")"
previous_target="$(readlink "$previous_link")"
if [[ ! -d "$current_target" || ! -d "$previous_target" ]]; then
  echo "发布包链接无效，拒绝回滚。" >&2
  exit 1
fi
case "$current_target" in
  "$controlled_releases"/*) ;;
  *) echo "current 不在受控发布目录内，拒绝回滚。" >&2; exit 1 ;;
esac
case "$previous_target" in
  "$controlled_releases"/*) ;;
  *) echo "previous 不在受控发布目录内，拒绝回滚。" >&2; exit 1 ;;
esac
if [[ "$current_target" == "$previous_target" ]]; then
  echo "current 与 previous 指向同一版本，拒绝无效回滚。" >&2
  exit 1
fi

"$USER_BETA_ROOT/scripts/user-beta/backup.sh"
"$USER_BETA_ROOT/scripts/user-beta/supervisor-stop.sh"
ln -sfn "$previous_target" "$current_link"
ln -sfn "$current_target" "$previous_link"

if ! "$USER_BETA_ROOT/scripts/user-beta/supervisor-start.sh"; then
  echo "上一版启动失败，正在恢复原发布链接。" >&2
  "$USER_BETA_ROOT/scripts/user-beta/supervisor-stop.sh" || true
  ln -sfn "$current_target" "$current_link"
  ln -sfn "$previous_target" "$previous_link"
  "$USER_BETA_ROOT/scripts/user-beta/supervisor-start.sh"
  exit 1
fi

echo "用户环境已回滚到发布包：$(tr -d '\n' < "$previous_target/RELEASE_ID")"
