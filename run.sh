#!/bin/sh
umask 077
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
exec /usr/bin/python3 "$ROOT/lite.py" scheduled --submit --status-path /www/moonuestc/status.json > "$ROOT/last-run.log" 2>&1
