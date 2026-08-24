#!/usr/bin/env bash

set -euo pipefail

release_resolve_controlled_dir() {
  local target="$1"
  shift
  [[ -d "$target" ]] || return 1

  local resolved_target
  resolved_target="$(cd "$target" && pwd -P)" || return 1
  local allowed_root resolved_root
  for allowed_root in "$@"; do
    [[ -d "$allowed_root" ]] || continue
    resolved_root="$(cd "$allowed_root" && pwd -P)" || continue
    case "$resolved_target" in
      "$resolved_root"/*)
        printf '%s\n' "$resolved_target"
        return 0
        ;;
    esac
  done
  return 1
}

release_web_server_path() {
  local release_dir="$1"
  local web_root="$release_dir/apps/web"
  local path_file="$web_root/WEB_SERVER_PATH"
  [[ -f "$path_file" ]] || return 1

  local relative_server
  relative_server="$(tr -d '\r\n' < "$path_file")"
  [[ -n "$relative_server" && "$relative_server" != /* ]] || return 1
  case "/$relative_server/" in
    */../*|*/./*) return 1 ;;
  esac

  local server_dir resolved_web_root resolved_server
  server_dir="$web_root/$(dirname "$relative_server")"
  [[ -d "$server_dir" ]] || return 1
  resolved_web_root="$(cd "$web_root" && pwd -P)" || return 1
  resolved_server="$(cd "$server_dir" && pwd -P)/$(basename "$relative_server")"
  case "$resolved_server" in
    "$resolved_web_root"/*) ;;
    *) return 1 ;;
  esac
  [[ -f "$resolved_server" && "$(basename "$resolved_server")" == "server.js" ]] || return 1
  printf '%s\n' "$resolved_server"
}

release_validate_runtime_layout() {
  local release_dir="$1"
  [[ -f "$release_dir/RELEASE_ID" ]] || return 1
  [[ -f "$release_dir/apps/api/app/main.py" ]] || return 1
  if [[ -f "$release_dir/apps/web/WEB_SERVER_PATH" ]]; then
    release_web_server_path "$release_dir" >/dev/null
    return
  fi
  [[ -x "$release_dir/apps/web/node_modules/.bin/next" ]]
}
