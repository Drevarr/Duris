#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/tests/async/disposable_schema.sh"

python3 "$ROOT/tests/async/guild_frags_load_mysql_harness.py"
