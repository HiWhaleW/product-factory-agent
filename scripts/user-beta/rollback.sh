#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
# shellcheck source=../release/lib.sh
source "$USER_BETA_ROOT/scripts/release/lib.sh"
user_beta_load_env
user_beta_python "$USER_BETA_ROOT/scripts/user-beta/ops.py" preflight

current_link="$USER_BETA_RUNTIME/current"
previous_link="$USER_BETA_RUNTIME/previous"
internal_releases="$USER_BETA_ROOT/.runtime/seed-beta/releases"
user_releases="$USER_BETA_RUNTIME/releases"

if [[ ! -L "$current_link" || ! -L "$previous_link" ]]; then
  echo "用户环境尚无上一版安全版本，拒绝回滚；请先完成下一版内部验收并发布。" >&2
  exit 1
fi

if ! current_target="$(release_resolve_controlled_dir \
  "$(readlink "$current_link")" "$internal_releases" "$user_releases")"; then
  echo "current 不在受控发布目录内，拒绝回滚。" >&2
  exit 1
fi
if ! previous_target="$(release_resolve_controlled_dir \
  "$(readlink "$previous_link")" "$internal_releases" "$user_releases")"; then
  echo "previous 不在受控发布目录内，拒绝回滚。" >&2
  exit 1
fi
if [[ "$current_target" == "$previous_target" ]]; then
  echo "current 与 previous 指向同一版本，拒绝无效回滚。" >&2
  exit 1
fi
for target in "$current_target" "$previous_target"; do
  if ! release_validate_runtime_layout "$target"; then
    echo "发布包运行结构无效，拒绝回滚。" >&2
    exit 1
  fi
  if [[ -f "$target/RELEASE-MANIFEST.sha256" ]]; then
    "$USER_BETA_ROOT/.venv/bin/python" \
      "$USER_BETA_ROOT/scripts/release/build_release.py" verify \
      --release-dir "$target"
  fi
done

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
