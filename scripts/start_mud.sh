#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1

nohup setsid ./scripts/cycle_mud.sh "$@" < /dev/null > logs/duris-console.log 2>&1 &
echo "DurisMUD started; console output is in logs/duris-console.log."
