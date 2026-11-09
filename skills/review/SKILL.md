---
name: review
description: >
  Review code changes on the current branch against main with risk-based routing.
  Use this skill whenever the user asks to "review my branch", "check my changes",
  "code review", "review this PR", "what did I change", or any variation of reviewing
  uncommitted or unmerged work. Trigger even if the user just says "can you check
  this branch" or "look at my changes" — they almost certainly want a risk-routed
  code review.
  Entry point: @review
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

## Step 1: Select the Scope

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
rules from Step 2 into the prompt.

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

Determine the label and create the artifacts directory. The label comes from the
branch name — the ticket key when the branch carries one, otherwise the branch
name with `/` replaced by `-`. Without this, `@review` on `fix/typo` writes to a
nonexistent `.agents/artifacts/fix/` directory.

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

```bash
mkdir -p .agents/artifacts
```

<!-- artifact-label:begin — shared verbatim across @arch, @build, @review, @ship and @reviewer; make lint-agents checks identity -->
```bash
TICKET=$(git branch --show-current | grep -oE '[A-Z]+-[0-9]+' | head -1)
LABEL=${TICKET:-$(git branch --show-current | tr '/' '-')}
```
<!-- artifact-label:end -->

Record the commit that was reviewed, so `@ship` can tell whether the review still
matches HEAD:

```bash
REVIEWED_HEAD=$(git rev-parse HEAD)
```

Derive the status from the reviewer's findings:

- `status: clean` — no Critical or Warning findings
- `status: has-findings` — any Critical or Warning items present

Write `.agents/artifacts/<LABEL>-review-impl.md`:

```yaml
---
artifact: review-impl
ticket: <TICKET>
skill: review
created: <ISO 8601 timestamp>
reviewed_head: <REVIEWED_HEAD>
status: clean        # or: has-findings
---
```

Followed by the reviewer's full report.

`@ship` reads this artifact, checks that `reviewed_head` still matches HEAD (or
that only `fixup!` commits follow), and blocks on `status: has-findings`.

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
