---
name: handoff
description: >
  Compact the current conversation into a handoff document so a fresh agent
  (in Claude Code or OpenCode) can continue the work. Writes the doc under
  .agents/handoffs/ and, after you confirm, syncs .agents/STATE.md for the next
  session. Use when the user says "handoff", "write a handoff", "prepare a
  handoff for the next session", or is ending a session mid-work.
  Entry point: @handoff [what the next session will focus on]
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent
can continue the work without re-reading this session.

---

## Gotchas

- Always write the handoff under `.agents/handoffs/`, never the project root or
  the OS temp dir BECAUSE `.agents/` is the agent's own disposable workspace
  (gitignored), `$TMPDIR` is empty on some machines, and a root-level file breaks
  `make lint-*` and `git status`.
- Always update .agents/STATE.md (position, current_branch, decisions, blockers)
  BECAUSE that is what `@arch` reads to bootstrap the next session.
- Always show the handoff and confirm before writing STATE.md BECAUSE STATE.md is
  the shared resume point and a wrong position sends the next session off course.
- Never duplicate content already in artifacts (.agents/artifacts/*), specs, plans,
  ADRs, commits, or diffs — reference them by relative path or URL instead BECAUSE
  duplicating causes the two copies to drift.
- Always redact API keys, passwords, tokens, and PII BECAUSE the handoff may be
  shared or left on disk.

---

## Step 1: Gather Context

Read the current position:
- `.agents/STATE.md` (branch, stage, decisions, blockers) — create on the fly if absent
- The most recent files in `.agents/artifacts/` (plan, impl-progress, review)
- Current branch and `git status`

## Step 2: Determine Next Focus

If the user passed an argument, tailor the doc to that focus. Otherwise use the
`position` in STATE.md to infer the next step (e.g. `implementing` → next is
`review`).

## Step 3: Write the Handoff

Write to `.agents/handoffs/<timestamp>.md` with a bash heredoc, containing:

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

```bash
mkdir -p .agents/handoffs
ts=$(date +%Y%m%d-%H%M%S)
HANDOFF=".agents/handoffs/$ts.md"
cat > "$HANDOFF" <<'EOF'
# Handoff
...
EOF
echo "$HANDOFF"
```

## Step 4: Confirm

Show the handoff path and a 3-line summary, then ask the user to confirm before
writing STATE.md.

## Step 5: Sync STATE.md (after confirmation)

Only after the user confirms, update `.agents/STATE.md` (creating it if absent)
with the new `position`, `current_branch`, `last_updated`, and any
decisions/blockers surfaced during the session. Keep it lean — decisions,
blockers, and position only. Set `position` to point at the handoff file, e.g.
`position: handoff written — .agents/handoffs/<ts>.md; next session: <focus>`.

---

## Quality Bar

A good handoff should:
- Let a fresh agent continue with zero questions to the user
- Reference artifacts rather than duplicating them
- Be free of secrets
- Leave STATE.md consistent so the next session reads the correct position
