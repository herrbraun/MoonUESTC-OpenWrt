#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$ROOT/.venv/bin/python" "$ROOT/linux_schedule.py" --remove
