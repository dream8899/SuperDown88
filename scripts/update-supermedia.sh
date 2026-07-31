#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=${SUPERMEDIA_ROOT:-"$PWD/Video_Download"}
exec python3 "$SCRIPT_DIR/supermedia_console.py" --root "$ROOT" update
