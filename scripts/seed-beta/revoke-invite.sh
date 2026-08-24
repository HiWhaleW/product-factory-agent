#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
seed_beta_load_env
seed_beta_python revoke-invite "$@"
