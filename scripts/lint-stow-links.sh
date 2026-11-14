#!/usr/bin/env bash
# lint-stow-links.sh — Fail when a symlink under stow/ does not resolve.
#
# Run after gen-stow.sh and build-claude.sh (`make lint-links` does both).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -d "$ROOT/stow" ] || { echo "FAIL  stow/ not found — run make link first"; exit 1; }

ok=true
count=0
while IFS= read -r -d '' l; do
  count=$((count + 1))
  if [ ! -e "$l" ]; then
    echo "FAIL  broken link: ${l#"$ROOT"/} -> $(readlink "$l")"
    ok=false
  fi
done < <(find "$ROOT/stow" -type l -print0)
[ "$count" -gt 0 ] || { echo "FAIL  stow/ holds no links"; exit 1; }
$ok && echo "OK    $count stow links resolve"
