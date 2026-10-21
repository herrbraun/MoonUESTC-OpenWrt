#!/bin/sh
umask 077
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)" || exit 1
exec /usr/bin/python3 "$ROOT/multi.py" checkin --due --submit > "$ROOT/last-run.log" 2>&1
