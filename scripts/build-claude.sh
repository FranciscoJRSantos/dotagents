#!/usr/bin/env bash
# build-claude.sh — Generate the Claude Code agent variants.
#
# Usage:
#   build-claude.sh <source-dir> <out-dir>
#
# Writes one <out-dir>/<agent>.md per agents/*.md. `make link` points
# ~/.claude/agents/ at the output through the stow package, and lint-agents
# validates it. The output is build output (gitignored).
set -euo pipefail

command -v yq >/dev/null 2>&1 && yq --version 2>&1 | grep -q mikefarah || {
  echo "FAIL  mikefarah yq not found — install it (mise use yq); build-claude.sh needs it" >&2
  exit 1
}

# claude_tools <agent.md> — derive the Claude Code `tools` allowlist from the
# OpenCode `permissions` list. Read/Grep/Glob are always present; Bash is added
# when shell is allowed on "*"; Edit/Write only when edits are not denied on "*"
# (Claude's flat tool list can't express a ".agents/**" edit exception).
claude_tools() {
  local file="$1" fm shell_allow edit_deny
  local tools="Read, Grep, Glob"
  fm="$(sed -n '1,/^---$/p' "$file")"
  shell_allow="$(printf '%s\n' "$fm" | yq eval 'select(di==0) | [.permissions[]? | select(.action=="shell" and .resource=="*" and .effect=="allow")] | length' | head -1)"
  edit_deny="$(printf '%s\n' "$fm" | yq eval 'select(di==0) | [.permissions[]? | select(.action=="edit" and .resource=="*" and .effect=="deny")] | length' | head -1)"
  [[ "$shell_allow" =~ ^[0-9]+$ && "$edit_deny" =~ ^[0-9]+$ ]] || { echo "FAIL  could not read permissions of $file" >&2; exit 1; }
  if [ "$shell_allow" -gt 0 ]; then
    tools="$tools, Bash"
  fi
  if [ "$edit_deny" -eq 0 ]; then
    tools="$tools, Edit, Write"
  fi
  # deferred: flat tool list drops the .agents/** edit exception, per-path Edit if Claude supports scoped tool rules
  printf '%s' "$tools"
}

# generate_claude_variants <source-dir> <out-dir> — emit one Claude Code variant
# per agent. The frontmatter is rebuilt (name from the filename, model: inherit,
# tools derived from permissions); the body is copied unchanged.
generate_claude_variants() {
  local src="$1" out="$2" f name desc tools body
  mkdir -p "$out"
  for f in "$src"/*.md; do
    [ -e "$f" ] || continue
    name="$(basename "$f" .md)"
    desc="$(sed -n '1,/^---$/p' "$f" | yq eval 'select(di==0) | .description // ""' 2>/dev/null | grep -v '^null$' | head -1)"
    tools="$(claude_tools "$f")"
    body="$(awk 'BEGIN{n=0} /^---$/{n++; if(n==2){p=1; next}} p' "$f")"
    {
      printf -- '---\n'
      NAME="$name" DESC="$desc" TOOLS="$tools" yq -n \
        '{"name": strenv(NAME), "description": strenv(DESC), "model": "inherit", "tools": strenv(TOOLS)}'
      printf -- '---\n'
      printf '%s\n' "$body"
    } > "$out/$name.md"
  done
}

SOURCE_DIR="${1:?usage: build-claude.sh <source-dir> <out-dir>}"
OUT_DIR="${2:?usage: build-claude.sh <source-dir> <out-dir>}"

rm -rf "$OUT_DIR"
generate_claude_variants "$SOURCE_DIR" "$OUT_DIR"
