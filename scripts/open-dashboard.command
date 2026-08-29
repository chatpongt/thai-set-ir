#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Thai SET IR Universe — one-click local dashboard launcher (macOS)
#
# Double-click this file to serve the dashboard from your machine and open it
# in your default browser. It reads the latest data/companies.js on disk, so
# you see edits before you push.
#
# Tip: put a shortcut on your Desktop without moving the file —
#   drag this file to the Desktop while holding ⌘ + ⌥ (makes an alias), or run:
#   ln -s "$(pwd)/scripts/open-dashboard.command" ~/Desktop/
# Double-clicking the alias runs the real script, so repo paths stay correct.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# Repo root = parent of this script's directory (script lives in scripts/).
# Resolves symlinks so a Desktop alias still finds the real repo.
SOURCE="${BASH_SOURCE[0]:-$0}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ "$SOURCE" != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

if [ ! -f "$ROOT/index.html" ]; then
  echo "❌ ไม่พบ index.html ใน $ROOT — วางไฟล์นี้ไว้ใน scripts/ ของ repo"
  read -n1 -rsp "กดปุ่มใดก็ได้เพื่อปิด..."; echo; exit 1
fi

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "❌ ไม่พบ python3 — ติดตั้งก่อนที่ https://www.python.org/downloads/"
  read -n1 -rsp "กดปุ่มใดก็ได้เพื่อปิด..."; echo; exit 1
fi

# Find a free TCP port starting at 8137.
PORT=8137
while lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; do
  PORT=$((PORT + 1))
done

URL="http://localhost:$PORT/index.html"
SRV=""
cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null || true; echo; echo "👋 หยุด server แล้ว"; }
trap cleanup INT TERM EXIT

echo "🚀 Thai SET IR Universe — local dashboard"
echo "   ที่มา : $ROOT"
echo "   เปิด  : $URL"
echo "   (ปิดหน้าต่างนี้ หรือกด Control-C เพื่อหยุด)"
echo

# Start the static server, wait for it to accept connections, then open browser.
"$PY" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &
SRV=$!
for _ in $(seq 1 20); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/index.html" && break
  sleep 0.25
done
open "$URL"

# Keep the server (and this window) alive until closed.
wait "$SRV"
