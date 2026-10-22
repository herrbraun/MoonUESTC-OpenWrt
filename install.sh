#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
umask 077
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'
if [ ! -x "$ROOT/.venv/bin/python" ]; then python3 -m venv "$ROOT/.venv"; fi
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
"$ROOT/.venv/bin/python" "$ROOT/lite.py" selftest
exec "$ROOT/.venv/bin/python" "$ROOT/tools/install_platform.py"
