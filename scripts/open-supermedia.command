#!/bin/zsh
# Reuse the existing local dashboard rather than starting a second server.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_ROOT="/Users/solo/Desktop/AI工作室/Video_Download"
ROOT="${SUPERMEDIA_ROOT:-$DEFAULT_ROOT}"
URL="http://127.0.0.1:8765"

if python3 - "$URL/api/dashboard" <<'PY'
import sys
from urllib.request import urlopen

try:
    with urlopen(sys.argv[1], timeout=1.5) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except OSError:
    raise SystemExit(1)
PY
then
  open "$URL"
  exit 0
fi

exec python3 "$SCRIPT_DIR/supermedia_console.py" --root "$ROOT" serve --open
