#!/usr/bin/env bash

set -euo pipefail

# shellcheck source=lib.sh
source "$(cd "$(dirname "$0")" && pwd -P)/lib.sh"
seed_beta_load_env
# A pre-migration backup is required precisely when the checked-in Alembic head
# is newer than the live database. pg_dump is safe without requiring revision
# equality; the generated metadata records the live revision for restore audit.
seed_beta_python backup
