#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
# shellcheck source=../release/lib.sh
source "$SEED_BETA_ROOT/scripts/release/lib.sh"
seed_beta_load_env
seed_beta_python preflight

current_link="$SEED_BETA_RUNTIME/current"
previous_link="$SEED_BETA_RUNTIME/previous"
if [[ ! -L "$current_link" || ! -L "$previous_link" ]]; then
  echo "缺少 current 或 previous 发布包，无法执行应用回滚。" >&2
  exit 1
fi
if ! current_target="$(release_resolve_controlled_dir \
  "$(readlink "$current_link")" "$SEED_BETA_RUNTIME/releases")"; then
  echo "current 不在受控 releases 目录内，拒绝回滚。" >&2
  exit 1
fi
if ! previous_target="$(release_resolve_controlled_dir \
  "$(readlink "$previous_link")" "$SEED_BETA_RUNTIME/releases")"; then
  echo "previous 不在受控 releases 目录内，拒绝回滚。" >&2
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
    "$SEED_BETA_ROOT/.venv/bin/python" \
      "$SEED_BETA_ROOT/scripts/release/build_release.py" verify \
      --release-dir "$target"
  fi
done

"$SEED_BETA_ROOT/scripts/seed-beta/backup.sh"
"$SEED_BETA_ROOT/scripts/seed-beta/stop.sh"
ln -sfn "$previous_target" "$current_link"
ln -sfn "$current_target" "$previous_link"
if ! "$SEED_BETA_ROOT/scripts/seed-beta/start.sh"; then
  echo "上一版启动失败，正在恢复原发布链接。" >&2
  "$SEED_BETA_ROOT/scripts/seed-beta/stop.sh" || true
  ln -sfn "$current_target" "$current_link"
  ln -sfn "$previous_target" "$previous_link"
  "$SEED_BETA_ROOT/scripts/seed-beta/start.sh"
  exit 1
fi

echo "应用已回滚到发布包：$(basename "$previous_target")"
