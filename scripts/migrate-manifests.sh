#!/usr/bin/env bash
# migrate-manifests.sh — One-time migration from the manifest deploy to stow.
#
# Usage: migrate-manifests.sh [--dry-run]   (HOME selects the home to migrate)
#
# For every target the old deploy wrote a .personal-agents-manifest into, remove
# exactly the entries it lists (when they are real files or dirs, not links) and
# then the manifest itself, so `stow` can put symlinks in their place. Entries
# not in a manifest (synced/, nono-sandbox.ts, artifacts/ ...) are never touched.
# A deployed copy that differs from its repo source (edited in place, or stale) is
# moved to $PRE_STOW_BACKUP instead of deleted; so is the rules copy, as
# AGENTS.md.pre-stow, when it differs from global/AGENTS.md. Manifest lines that
# are not plain names are skipped, and a symlinked target is refused. Safe to
# re-run: with no manifests left it does nothing.
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGETS=(
  "$HOME/.config/opencode/skills"
  "$HOME/.config/opencode/agents"
  "$HOME/.config/opencode/plugins"
  "$HOME/.claude/skills"
  "$HOME/.claude/agents"
  "$HOME/.agents"
)

PRE_STOW_BACKUP="${PRE_STOW_BACKUP:-$HOME/.local/state/dotagents-pre-stow/$(date +%Y%m%d-%H%M%S)}"

# source_for <target> <name> — the repo path a deployed entry was copied from.
source_for() {
  case "$1" in
    "$HOME/.config/opencode/skills" | "$HOME/.claude/skills") echo "$ROOT/skills/$2" ;;
    "$HOME/.config/opencode/agents") echo "$ROOT/agents/$2" ;;
    "$HOME/.config/opencode/plugins") echo "$ROOT/plugins/$2" ;;
    "$HOME/.claude/agents") echo "$ROOT/build/claude-agents/$2" ;;
    "$HOME/.agents") case "$2" in partials) echo "$ROOT/agents/partials" ;; *) echo "$ROOT/$2" ;; esac ;;
  esac
}

run() { if [ "$DRY" = 1 ]; then echo "would: $*"; else "$@"; fi; }

for target in "${TARGETS[@]}"; do
  manifest="$target/.personal-agents-manifest"
  [ -f "$manifest" ] || continue
  if [ -L "$target" ]; then
    echo "ERROR target is a symlink; refusing to remove entries through it: $target" >&2
    exit 1
  fi
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    case "$name" in
      */* | . | ..) echo "WARN  skipping unsafe manifest entry '$name' in $manifest" >&2; continue ;;
    esac
    path="$target/$name"
    if [ -L "$path" ]; then
      echo "keep   $path (already a link)"
    elif [ -e "$path" ]; then
      src="$(source_for "$target" "$name")"
      if [ -n "$src" ] && [ -e "$src" ] && ! diff -rq "$path" "$src" >/dev/null 2>&1; then
        dest="$PRE_STOW_BACKUP/${target#"$HOME"/}"
        echo "backup $path -> $dest/$name (differs from the repo source)"
        run mkdir -p "$dest"
        run mv -- "$path" "$dest/$name"
      else
        echo "remove $path"
        run rm -rf -- "$path"
      fi
    fi
  done < "$manifest"
  echo "remove $manifest"
  run rm -f -- "$manifest"
done

rules="$HOME/.config/opencode/AGENTS.md"
if [ -f "$rules" ] && [ ! -L "$rules" ] && [ -f "$ROOT/global/AGENTS.md" ]; then
  if cmp -s "$rules" "$ROOT/global/AGENTS.md"; then
    echo "remove $rules (identical to global/AGENTS.md)"
    run rm -f -- "$rules"
  else
    echo "move   $rules -> $rules.pre-stow (differs from global/AGENTS.md)"
    run mv -- "$rules" "$rules.pre-stow"
  fi
fi
