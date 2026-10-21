#!/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ "$(id -u)" != 0 ]; then
    printf '%s\n' 'Run on OpenWrt as root.' >&2
    exit 1
fi
case "$ROOT" in
    *[!A-Za-z0-9_./-]*) printf '%s\n' 'Use a directory without spaces or special characters.' >&2; exit 1 ;;
esac
umask 077
chmod 700 "$ROOT"
chmod 600 "$ROOT/config.json"
python3 "$ROOT/lite.py" selftest
exec python3 "$ROOT/tools/install.py"
