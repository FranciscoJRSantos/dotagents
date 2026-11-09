---
name: handoff
description: >
  Compact the current conversation into a handoff document so a fresh agent
  (in Claude Code or OpenCode) can continue the work. When a work folder is
  active, writes to <slug>/handoffs/<timestamp>.org; otherwise falls back to
  .agents/handoffs/<timestamp>.org. After you confirm, syncs .agents/STATE.org
  for the next session. Use when the user says "handoff", "write a handoff",
  "prepare a handoff for the next session", or is ending a session mid-work.
  Entry point: @handoff [what the next session will focus on]
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent
can continue the work without re-reading this session.

---

## Gotchas

- When `ARTIFACT_DIR` is set (a work folder is active), write the handoff to
  `$ARTIFACT_DIR/handoffs/<timestamp>.org` BECAUSE handoffs belong to the work
  they describe, and archiving the folder moves them together.
- When no work folder is active, fall back to `.agents/handoffs/<timestamp>.org`
  BECAUSE handoffs still need a stable location, but they are not tied to any
  specific piece of work.
- Never write the handoff to the project root or the OS temp dir BECAUSE
  `.agents/` is the agent's own disposable workspace (gitignored), `$TMPDIR` is
  empty on some machines, and a root-level file breaks `make lint-*` and `git status`.
- Always update `.agents/STATE.org` (position, current_branch, decisions, blockers)
  BECAUSE that is what `@arch` reads to bootstrap the next session.
- Always show the handoff and confirm before writing STATE.org BECAUSE STATE.org is
  the shared resume point and a wrong position sends the next session off course.
- Never duplicate content already in artifacts (.agents/artifacts/*), specs, plans,
  ADRs, commits, or diffs — reference them by relative path or URL instead BECAUSE
  duplicating causes the two copies to drift.
- Always redact API keys, passwords, tokens, and PII BECAUSE the handoff may be
  shared or left on disk.

---

## Step 0: Resolve the Work Folder

```bash
OUT=$(~/.agents/bin/artifact-dir ""); rc=$?
echo "$OUT"
if [ $rc -eq 0 ]; then
  ARTIFACT_DIR=$(echo "$OUT" | sed -n 's/^ARTIFACT_DIR=//p')
  echo "Work folder: $ARTIFACT_DIR"
else
  echo "No active work folder — using .agents/handoffs/"
  unset ARTIFACT_DIR
fi
```

If `ARTIFACT_DIR` is set, handoffs go to `$ARTIFACT_DIR/handoffs/`; otherwise to
`.agents/handoffs/`.

---

## Step 1: Gather Context

Read the current position:
- `.agents/STATE.org` (branch, stage, decisions, blockers) — create on the fly if absent
- The most recent files in `.agents/artifacts/` (plan.org, board.org, review.org)
- Current branch and `git status`

## Step 2: Determine Next Focus

If the user passed an argument, tailor the doc to that focus. Otherwise use the
`#+POSITION:` keyword in STATE.org to infer the next step (e.g. `implementing` → next is
`review`).

## Step 3: Write the Handoff

Write to `$ARTIFACT_DIR/handoffs/<timestamp>.org` (when a work folder is active) or
`.agents/handoffs/<timestamp>.org` (fallback), containing:

- **Current state** — branch, stage, what is done and what is not
- **Context** — references to artifacts/plans/ADRs by path, never duplicated
- **Next actions** — concrete, ordered, matching the current workflow stage
- **Suggested skills** — which repo skills to invoke next (`@spec`, `@arch`,
  `@build`, `@review`, `@ship`, `@codemap`), with the entry point
- **Redactions** — note anything deliberately omitted for secrecy

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

### 3a. Write as Markdown first

```bash
if [ -n "${ARTIFACT_DIR:-}" ]; then
  mkdir -p "$ARTIFACT_DIR/handoffs"
  ts=$(date +%Y%m%d-%H%M%S)
  HANDOFF_MD=$(mktemp --suffix=.md)
  HANDOFF_ORG="$ARTIFACT_DIR/handoffs/$ts.org"
else
  mkdir -p .agents/handoffs
  ts=$(date +%Y%m%d-%H%M%S)
  HANDOFF_MD=$(mktemp --suffix=.md)
  HANDOFF_ORG=".agents/handoffs/$ts.org"
fi

cat > "$HANDOFF_MD" <<'EOF'
# Handoff: <title>

**Branch:** <branch>
**Position:** <one-line position>
**Last updated:** <ISO 8601 timestamp>

---

## Current State

<what is done and what is not>

---

## Context

<references to artifacts/plans/ADRs by path, never duplicated>

---

## Next Actions

<concrete, ordered list matching the current workflow stage>

---

## Suggested Skills

- **@<skill>** — <what to do with it>

---

## Redactions

<Anything deliberately omitted for secrecy, or "None.">
EOF
```

### 3b. Convert to Org

```bash
BRANCH=$(git branch --show-current)
TICKET=$(echo "$BRANCH" | grep -oE '[A-Z]+-[0-9]+' | head -1 || true)

~/.agents/bin/md2org "$HANDOFF_MD" "$HANDOFF_ORG" \
  TITLE="Handoff: <title>" \
  BRANCH="$BRANCH" \
  ${TICKET:+TICKET="$TICKET"} \
  POSITION="<position>" && rm -f "$HANDOFF_MD"

echo "$HANDOFF_ORG"
```

`md2org` must exit 0 before you continue. On a non-zero exit it prints `file:line`
per Markdown leftover and keeps both files: fix the lines in `$HANDOFF_MD` and run it
again.

## Step 4: Confirm

Show the handoff path and a 3-line summary, then ask the user to confirm before
writing STATE.org.

## Step 5: Sync STATE.org (after confirmation)

Only after the user confirms, update `.agents/STATE.org` (creating it if absent)
with the new position, branch, and any decisions/blockers surfaced during the
session. The block rewrites the keyword header — keeping `#+CREATED:` and
everything below the header — and creates the file with empty `* Decisions` and
`* Blockers` sections when it is missing:

```bash
STATE=.agents/STATE.org
POSITION=<position — include handoff file path and next session focus>
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CREATED=$(grep -m1 '^#+CREATED:' "$STATE" 2>/dev/null | cut -d' ' -f2)
BODY=$(sed '1,/^$/d' "$STATE" 2>/dev/null)
{
  printf '#+TITLE: State\n#+CREATED: %s\n#+UPDATED: %s\n#+BRANCH: %s\n#+POSITION: %s\n\n' \
    "${CREATED:-$NOW}" "$NOW" "$(git branch --show-current)" "$POSITION"
  printf '%s\n' "${BODY:-$(printf '* Decisions\n\n* Blockers')}"
} > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
~/.agents/bin/org-check "$STATE"
```

Add any new decisions under `* Decisions` and blockers under `* Blockers`, one
`- <YYYY-MM-DD> — <text>` item each, in Org markup (`=path=`, `~code~`, never
backticks). Run `org-check "$STATE"` again; it must pass.

Keep it lean — decisions, blockers, and position only. Set `#+POSITION:` to point
at the handoff file, e.g. `handoff written — <slug>/handoffs/<ts>.org; next session: <focus>`.

---

## Quality Bar

A good handoff should:
- Let a fresh agent continue with zero questions to the user
- Reference artifacts rather than duplicating them
- Be free of secrets
- Leave STATE.org consistent so the next session reads the correct position
- Use Org markup in STATE.org (`=path=`, `~code~`), never backticks
