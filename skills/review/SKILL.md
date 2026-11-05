---
name: review
description: >
  Review code changes on the current branch against main. Use this skill whenever
  the user asks to "review my branch", "check my changes", "code review", "review
  this PR", "what did I change", or any variation of reviewing uncommitted or
  unmerged work. Trigger even if the user just says "can you check this branch" or
  "look at my changes" — they almost certainly want a structured code review.
---

# Review Skill

A thin wrapper: select the diff scope, load the project's review rules, spawn the
`reviewer` agent, then write the review artifact. The review rules, specialist
frames and output format live only in `~/.agents/partials/review-rules.md` — do
not duplicate them here or in the reviewer.

---

## Step 1: Select the Scope

Pick one:

- **branch** (default) — the whole branch: from the merge base with the default
  branch through the working tree, including untracked files. Use this for the
  final review before `@ship`.
- **slice** — the current slice only: `git diff HEAD` plus untracked files. Use
  this when reviewing work inside a single `@implement` slice.

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

## Step 3: Spawn the reviewer

Spawn the `reviewer` subagent with the scope named explicitly in the invocation —
`@reviewer branch` (default) or `@reviewer slice` — and paste any project review
rules from Step 2 into the prompt.

The reviewer acquires the diff itself and returns the review report, ending with
the `GATE:` line. Do not re-run the review in the main context.

---

## Step 4: Write the Artifact

Determine the label and create the artifacts directory. The label comes from the
branch name — the ticket key when the branch carries one, otherwise the branch
name with `/` replaced by `-`. Without this, `/review` on `fix/typo` writes to a
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

<!-- artifact-label:begin — shared verbatim across @plan, @implement, /review, @ship and @reviewer; make lint-agents checks identity -->
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
