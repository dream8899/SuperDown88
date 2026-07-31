#!/bin/zsh
# macOS Finder launcher. The Terminal stays open so results remain reviewable.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_ROOT="/Users/solo/Desktop/AI工作室/Video_Download"
ROOT="${SUPERMEDIA_ROOT:-$DEFAULT_ROOT}"
python3 "$SCRIPT_DIR/supermedia_console.py" --root "$ROOT" update
printf '\n完成。按回车键关闭此窗口。'
read -r
