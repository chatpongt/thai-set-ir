#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Thai SET IR Universe — consolidate every local copy onto one drive (macOS)
#
# Keeps exactly ONE working copy, on the "1 TB" external drive, and removes
# copies sitting on any other drive (internal SSD, other volumes, iCloud, …).
#
# Usage:
#   bash scripts/consolidate-repo.sh                 # dry run — shows the plan
#   bash scripts/consolidate-repo.sh --apply         # actually move & delete
#   bash scripts/consolidate-repo.sh --apply --force # delete even if a copy has
#                                                    # uncommitted / unpushed work
#   bash scripts/consolidate-repo.sh --home /Volumes/MyDisk/thai-set-ir
#
# Nothing is deleted without --apply. A copy with uncommitted changes or commits
# that are not on origin is REFUSED unless you pass --force, so local work is
# never thrown away silently.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REMOTE_URL="https://github.com/chatpongt/thai-set-ir"
APPLY=0
FORCE=0
HOME_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --force) FORCE=1 ;;
    --home)  HOME_DIR="${2:-}"; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "❌ ไม่รู้จัก option: $1"; exit 2 ;;
  esac
  shift
done

# ── 1. Locate the "1 TB" drive ───────────────────────────────────────────────
if [ -z "$HOME_DIR" ]; then
  DRIVE=""
  for candidate in /Volumes/*; do
    [ -d "$candidate" ] || continue
    name="$(basename "$candidate")"
    # Match "1TB", "1 TB", "1Tb", "My 1TB Drive", … case-insensitively.
    if printf '%s' "$name" | grep -Eiq '1[[:space:]_-]?tb'; then
      DRIVE="$candidate"; break
    fi
  done
  if [ -z "$DRIVE" ]; then
    echo "❌ หาไดรฟ์ที่ชื่อมี \"1TB\" ใน /Volumes ไม่เจอ — เสียบไดรฟ์แล้วลองใหม่"
    echo "   หรือระบุเองด้วย: --home /Volumes/ชื่อไดรฟ์/thai-set-ir"
    echo "   ไดรฟ์ที่ต่ออยู่ตอนนี้:"; ls -1 /Volumes
    exit 1
  fi
  HOME_DIR="$DRIVE/thai-set-ir"
fi

# Normalise to an absolute path without requiring the directory to exist yet.
HOME_PARENT="$(cd "$(dirname "$HOME_DIR")" 2>/dev/null && pwd || true)"
if [ -z "$HOME_PARENT" ]; then
  echo "❌ ไม่พบโฟลเดอร์แม่ของ $HOME_DIR"; exit 1
fi
HOME_DIR="$HOME_PARENT/$(basename "$HOME_DIR")"

echo "🏠 ปลายทางที่จะเก็บงานไว้: $HOME_DIR"
[ "$APPLY" -eq 1 ] || echo "🔍 โหมด dry-run — ยังไม่ลบ/ย้ายอะไรทั้งนั้น (ใส่ --apply เพื่อทำจริง)"
echo

# ── 2. Find every copy of the repo on the machine ────────────────────────────
# A copy = a directory holding both index.html and data/companies.js whose git
# remote points at this repository. Search roots are every mounted volume plus
# the home folder, so both the external drives and the internal disk are covered.
# -maxdepth keeps the sweep quick; put the repo deeper than that and pass --home.
echo "🔎 กำลังค้นหา copy ทั้งหมด (อาจใช้เวลาสักครู่)…"
ROOTS=("$HOME")
for v in /Volumes/*; do [ -d "$v" ] && ROOTS+=("$v"); done

FOUND=()
while IFS= read -r marker; do
  dir="$(cd "$(dirname "$marker")/.." 2>/dev/null && pwd)" || continue
  [ -f "$dir/index.html" ] || continue
  [ -e "$dir/.git" ] || continue
  url="$(git -C "$dir" remote get-url origin 2>/dev/null || true)"
  case "$url" in
    *chatpongt/thai-set-ir*) ;;
    *) continue ;;
  esac
  # De-duplicate (a path can surface from more than one search root).
  dup=0
  for seen in ${FOUND+"${FOUND[@]}"}; do [ "$seen" = "$dir" ] && dup=1; done
  [ "$dup" -eq 1 ] && continue
  FOUND+=("$dir")
done < <(find "${ROOTS[@]}" -maxdepth 6 -type f -path '*/data/companies.js' 2>/dev/null)

if [ ${#FOUND[@]} -eq 0 ]; then
  echo "ℹ️  ไม่พบ copy ในเครื่องเลย"
else
  echo "พบ ${#FOUND[@]} copy:"
  for d in "${FOUND[@]}"; do echo "   • $d"; done
fi
echo

# ── 3. Make sure the canonical copy exists ───────────────────────────────────
KEEPER=""
MOVED_SRC=""
for d in ${FOUND+"${FOUND[@]}"}; do
  [ "$d" = "$HOME_DIR" ] && KEEPER="$d"
done

if [ -n "$KEEPER" ]; then
  echo "✅ มี copy อยู่ที่ปลายทางแล้ว: $KEEPER"
elif [ ${#FOUND[@]} -gt 0 ]; then
  SRC="${FOUND[0]}"
  echo "📦 จะย้าย $SRC → $HOME_DIR"
  MOVED_SRC="$SRC"
  if [ "$APPLY" -eq 1 ]; then
    mkdir -p "$(dirname "$HOME_DIR")"
    mv "$SRC" "$HOME_DIR"
    KEEPER="$HOME_DIR"
    # Drop the moved path from the delete list.
    REST=(); for d in "${FOUND[@]}"; do [ "$d" = "$SRC" ] || REST+=("$d"); done
    FOUND=(${REST+"${REST[@]}"})
    echo "   ย้ายเรียบร้อย"
  fi
else
  echo "📥 จะ clone ใหม่จาก $REMOTE_URL → $HOME_DIR"
  if [ "$APPLY" -eq 1 ]; then
    mkdir -p "$(dirname "$HOME_DIR")"
    git clone "$REMOTE_URL" "$HOME_DIR"
    KEEPER="$HOME_DIR"
  fi
fi
echo

# ── 4. Remove the copies on other drives ─────────────────────────────────────
SKIPPED=0
DELETED=0
for d in ${FOUND+"${FOUND[@]}"}; do
  [ "$d" = "$HOME_DIR" ] && continue
  [ -n "$MOVED_SRC" ] && [ "$d" = "$MOVED_SRC" ] && continue

  # Refuse to delete work that exists nowhere else.
  dirty=""
  [ -n "$(git -C "$d" status --porcelain 2>/dev/null)" ] && dirty="มีไฟล์ที่ยังไม่ commit"
  unpushed="$(git -C "$d" log --branches --not --remotes --oneline 2>/dev/null | head -5 || true)"
  [ -n "$unpushed" ] && dirty="${dirty:+$dirty + }มี commit ที่ยังไม่ push"

  if [ -n "$dirty" ] && [ "$FORCE" -eq 0 ]; then
    echo "⏭️  ข้าม $d — $dirty"
    [ -n "$unpushed" ] && echo "$unpushed" | sed 's/^/        /'
    echo "        push งานก่อน แล้วรันซ้ำ (หรือใช้ --force ถ้าจะทิ้งจริง ๆ)"
    SKIPPED=$((SKIPPED+1))
    continue
  fi

  echo "🗑️  ลบ $d${dirty:+  (--force: ทิ้ง $dirty)}"
  if [ "$APPLY" -eq 1 ]; then
    rm -rf "$d"
    DELETED=$((DELETED+1))
  fi
done

echo
echo "─────────────────────────────────────────"
if [ "$APPLY" -eq 1 ]; then
  echo "เสร็จแล้ว — เก็บไว้ที่ ${KEEPER:-$HOME_DIR}, ลบไป $DELETED copy, ข้าม $SKIPPED copy"
else
  echo "dry-run จบ — รันซ้ำพร้อม --apply เพื่อทำจริง"
fi
