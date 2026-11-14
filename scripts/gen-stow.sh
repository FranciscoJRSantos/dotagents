#!/usr/bin/env bash
# gen-stow.sh — Regenerate the stow/ packages from the repo sources.
#
# Each package is a tree of relative symlinks into skills/, agents/, plugins/,
# bin/ and global/, so `stow` links ~/.config/opencode, ~/.claude and ~/.agents
# straight at the repo and edits take effect in place. The packages are wiped and
# rebuilt on every run, so a deleted skill or agent drops out of stow/ and the
# next `stow -R` removes its live link.
#
#   stow/opencode     ~/.config/opencode/{skills,agents,plugins,AGENTS.md}
#   stow/claude       ~/.claude/{skills,agents}   (agents → build/claude-agents)
#   stow/agents-home  ~/.agents/{bin,partials}
#
# Usage: gen-stow.sh   (run from the repo root; `make link` does)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STOW_DIR="$ROOT/stow"
CLAUDE_AGENTS="build/claude-agents"

# link <package-relative dir> <name> <repo-relative target>
link() {
  local dir="$STOW_DIR/$1" name="$2" target="$ROOT/$3"
  mkdir -p "$dir"
  ln -s "$(realpath -m --relative-to="$dir" "$target")" "$dir/$name"
}

rm -rf "$STOW_DIR"

for d in "$ROOT"/skills/*/; do
  [ -e "$d" ] || continue
  n="$(basename "$d")"
  link opencode/.config/opencode/skills "$n" "skills/$n"
  link claude/.claude/skills "$n" "skills/$n"
done

for f in "$ROOT"/agents/*.md; do
  [ -e "$f" ] || continue
  n="$(basename "$f")"
  link opencode/.config/opencode/agents "$n" "agents/$n"
  link claude/.claude/agents "$n" "$CLAUDE_AGENTS/$n"
done

for d in "$ROOT"/plugins/*/; do
  [ -e "$d" ] || continue
  n="$(basename "$d")"
  link opencode/.config/opencode/plugins "$n" "plugins/$n"
done

# global/AGENTS.md is gitignored; without it the rules just are not linked.
if [ -f "$ROOT/global/AGENTS.md" ]; then
  link opencode/.config/opencode AGENTS.md global/AGENTS.md
else
  echo "WARN  global/AGENTS.md not found — rules not linked (create it from global/AGENTS.md.example)" >&2
fi

for f in "$ROOT"/bin/*; do
  link agents-home/.agents/bin "$(basename "$f")" "bin/$(basename "$f")"
done
link agents-home/.agents partials agents/partials

echo "stow packages generated in $STOW_DIR"
