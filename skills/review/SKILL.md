---
name: review
description: >
  Review code changes on the current branch against main with risk-based routing.
  Use this skill whenever the user asks to "review my branch", "check my changes",
  "code review", "review this PR", "what did I change", or any variation of reviewing
  uncommitted or unmerged work. Trigger even if the user just says "can you check
  this branch" or "look at my changes" — they almost certainly want a risk-routed
  code review.
  Entry point: @review [slug | scope]
---

# Review Skill

Risk-routed code review. The reviewer always runs, but risk classification determines
whether the human sees the full report or just a one-line evidence summary. The review
rules, specialist frames, risk classifier, and output format live in shared partials —
do not duplicate them here or in the reviewer.

**This is the HITL point in the factory model.** All implementation (`@build`) runs
autonomously. Only `@review` escalates to the human, and only when risk classification
says so.

---

## Conversation Density

**Conversation is routing only.** Keep conversation output to 1-3 lines.
Write all detail to artifacts. The user reads conversation for decisions, drills into
artifacts for detail.

- Full review report → artifact
- Evidence format → conversation (when escalated)
- Conversation: "Files: N | Risk: reason | Checks: ✅/❌" (when escalated)
- Conversation: "Review auto-passed. Files: N. Checks: ✅" (when clear)

---

## Subagent Routing

This skill spawns a `reviewer` subagent (Step 3). The reviewer **must use a different model family** than the orchestrator — never review with the same model that implemented the code.

**Required:** Spawn the reviewer with explicit model:
```
model: opencode-go/glm-5.3-flash
```

This keeps review independent (different family = independent signal) and off the company quota. See global `AGENTS.md` → "Model routing" for the canonical table.

---

## Step 1: Resolve the Work Folder

The invocation argument (`@review <arg>`) is a **slug** when `.agents/{artifacts,archive}/<arg>` exists, otherwise it is a **scope** (commit, branch, or MR). Resolve the folder first:

```bash
SLUG=<arg if it is a folder, else empty>
OUT=$(~/.agents/bin/artifact-dir "$SLUG"); rc=$?
echo "$OUT"
DIR=$(printf '%s\n' "$OUT" | sed -n 's/^ARTIFACT_DIR=//p')
```

- **`ARTIFACT_DIR=…`** (`rc` 0) — set `ARTIFACT_DIR="$DIR"` and pass it to the reviewer in Step 3. The reviewer reads `plan.org` and `board.org` from this folder for context.
- **`NONE`**, **`AMBIGUOUS: …`**, or **`NOT FOUND: <slug>`** — the argument was a scope, not a slug. Continue without `ARTIFACT_DIR`; the reviewer falls back to its own `artifact-dir` lookup (and skips plan context when unresolved).

A `LEGACY LAYOUT` warning on stderr means flat files from the old layout are present; they are ignored, so carry on.

---

## Step 1a: Select the Scope

Pick one:

- **branch** (default) — the whole branch: from the merge base with the default
  branch through the working tree, including untracked files. Use this for the
  final review before `@ship`.
- **slice** — the current slice only: `git diff HEAD` plus untracked files. Use
  this when reviewing work inside a single `@build` slice.

If the user did not specify a scope, use `branch`.

---

## Step 2: Load Project Review Rules

```bash
cat .agents/review.md 2>/dev/null
```

If it exists, pass its contents to the reviewer. It extends and overrides the
shared `~/.agents/partials/review-rules.md`. The only template for this file is
`templates/review.md.example`.

---

## Step 3: Spawn the Reviewer

Spawn the `reviewer` subagent with the scope named explicitly in the invocation —
`@reviewer branch` (default) or `@reviewer slice` — and paste any project review
rules from Step 2 into the prompt. Pass `ARTIFACT_DIR` when Step 1 resolved one:

```
ARTIFACT_DIR=$DIR
```

The reviewer reads `$ARTIFACT_DIR/plan.org` and `$ARTIFACT_DIR/board.org` for context when available, falls back to its own `artifact-dir` lookup, and skips plan context (never asks) when unresolved.

The reviewer acquires the diff itself and returns the review report, ending with
the `GATE:` line. Do not re-run the review in the main context.

---

## Step 4: Risk Classification

Load the risk classifier partial:

```bash
cat ~/.agents/partials/risk-classifier.md 2>/dev/null
```

**Pre-check:** If the reviewer's report has any Critical or Warning findings, skip classification and escalate immediately — the artifact will have `status: has-findings` and `@ship` will block regardless.

Otherwise, apply the classification logic from the partial:

1. **Check learned patterns** — if `.agents/review.md` has learned false positives,
   check if any changed file matches
2. **Check escalation classes** — auth, billing, schema, security, migrations, crypto
3. **Check heuristics** — file count > 10 or changes span > 3 directories
4. **Classify** — escalate or auto-pass

---

## Step 5: Route the Output

Based on the classification:

**If escalated:**
Show the evidence format in conversation:

```
Files: <N> | Risk: <reason> | Checks: ✅/❌
```

Write the full review report to the artifact. The user can drill into the artifact
for detail.

**If auto-passed:**
Show a one-liner in conversation:

```
Review auto-passed. Files: <N>. Checks: ✅
```

Write the review report to the artifact regardless (it's the source of truth).

---

## Step 6: Write the Artifact

Determine the artifact location. When Step 1 resolved a folder (`ARTIFACT_DIR` set), write `review.org` there. Otherwise, derive the slug from the current branch name and write to `.agents/artifacts/<slug>/review.org`, or abort if a slug cannot be derived.

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

Record the commit that was reviewed, so `@ship` can tell whether the review still
matches HEAD:

```bash
REVIEWED_HEAD=$(git rev-parse HEAD)
```

Derive the status from the reviewer's findings:

- `STATUS=clean` — no Critical or Warning findings
- `STATUS=has-findings` — any Critical or Warning items present

### With artifact folder

When `ARTIFACT_DIR` is set, write the reviewer's Markdown report to a temp file and convert it with `md2org`:

```bash
REPORT_MD=$(mktemp --suffix=.md)
cat > "$REPORT_MD" <<'EOF'
[paste the reviewer's full Markdown report here]
EOF

~/.agents/bin/md2org "$REPORT_MD" "$ARTIFACT_DIR/review.org" \
  REVIEWED_HEAD="$REVIEWED_HEAD" \
  STATUS="$STATUS" && rm -f "$REPORT_MD"
```

`md2org` must exit 0 before you continue. On a non-zero exit it prints `file:line`
per Markdown leftover and keeps both files: fix the lines in `$REPORT_MD` and run it
again.

The resulting `review.org` has `#+REVIEWED_HEAD:` and `#+STATUS:` keywords at the top, followed by the report body. `@ship` reads these keywords, checks that `REVIEWED_HEAD` still matches HEAD (or that only `fixup!` commits follow), and blocks on `STATUS: has-findings`.

If `ARTIFACT_DIR` is not set (the argument was a scope, not a slug), derive the slug from the current branch name and write the review report to `.agents/artifacts/<slug>/review.org`, or abort if a slug cannot be derived.

Run `/clear` before `@ship` to start the ship step in a fresh context window.

---

## Step 7: Learn from Overrides

If the user says the classification was wrong (e.g. "this didn't need review"),
update `.agents/review.md` with the learned pattern:

```markdown
## Learned Patterns

### False positives (don't escalate)
- <file pattern> — <reason> (learned <date>)
```

If the user says something should have been escalated, add it as a false negative.

This is the progressive learning from D2 — auto-learn from review outcomes.
