#!/usr/bin/env bash
# deploy-agents.sh — Deploy agent items to a target dir via the manifest sync.
#
# Usage:
#   deploy-agents.sh [--drift] <source-dir> <target-dir> <mode>
#   deploy-agents.sh --emit <out-dir> <source-dir>
#
# Modes:
#   --md-only        Top-level *.md files (for ~/.config/opencode/agents/)
#   --claude         Generated Claude Code variants (frontmatter rewritten)
#
#   --emit           Generate the Claude variants into <out-dir> and exit.
#                    Used by lint to validate the generated output.
#   --drift          Read-only diff (passed through to manifest-sync.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# claude_tools <agent.md> — derive the Claude Code `tools` allowlist from the
# OpenCode `permissions` list. Read/Grep/Glob are always present; Bash is added
# when shell is allowed on "*"; Edit/Write only when edits are not denied on "*"
# (Claude's flat tool list can't express a ".agents/**" edit exception).
claude_tools() {
  local file="$1" fm shell_allow edit_deny
  local tools="Read, Grep, Glob"
  fm="$(sed -n '1,/^---$/p' "$file")"
  shell_allow="$(printf '%s\n' "$fm" | yq eval 'select(di==0) | [.permissions[]? | select(.action=="shell" and .resource=="*" and .effect=="allow")] | length' 2>/dev/null | head -1)"
  edit_deny="$(printf '%s\n' "$fm" | yq eval 'select(di==0) | [.permissions[]? | select(.action=="edit" and .resource=="*" and .effect=="deny")] | length' 2>/dev/null | head -1)"
  if [ "${shell_allow:-0}" -gt 0 ]; then
    tools="$tools, Bash"
  fi
  if [ "${edit_deny:-0}" -eq 0 ]; then
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

if [ "${1:-}" = "--emit" ]; then
  OUT_DIR="${2:?usage: deploy-agents.sh --emit <out-dir> <source-dir>}"
  SOURCE_DIR="${3:?}"
  generate_claude_variants "$SOURCE_DIR" "$OUT_DIR"
  exit 0
fi

DRIFT=""
if [ "${1:-}" = "--drift" ]; then
  DRIFT="--drift"
  shift
fi

SOURCE_DIR="${1:?usage: deploy-agents.sh [--drift] <source-dir> <target-dir> <mode>}"
TARGET_DIR="${2:?}"
MODE="${3:-}"

declare -a ITEMS=()
case "$MODE" in
  --md-only)
    mapfile -t MD_FILES < <(find "$SOURCE_DIR" -maxdepth 1 -name "*.md" -print | sort)
    ITEMS+=("${MD_FILES[@]}")
    ;;
  --claude)
    STAGING="$(mktemp -d)"
    trap 'rm -rf "$STAGING"' EXIT
    generate_claude_variants "$SOURCE_DIR" "$STAGING"
    mapfile -t GEN_FILES < <(find "$STAGING" -maxdepth 1 -name "*.md" -print | sort)
    ITEMS+=("${GEN_FILES[@]}")
    ;;
  *)
    echo "ERROR unknown mode '${MODE:-<none>}' (use --md-only or --claude)" >&2
    exit 2
    ;;
esac

if [ ${#ITEMS[@]} -eq 0 ]; then
  echo "ERROR no agent items found in $SOURCE_DIR (mode ${MODE:-<none>})" >&2
  exit 2
fi

"$SCRIPT_DIR/manifest-sync.sh" $DRIFT "$TARGET_DIR" "${ITEMS[@]}"
