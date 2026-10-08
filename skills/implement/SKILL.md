---
name: implement
description: >
  Vertical-slice implementation with TDD inside each slice. Reads the plan and
  kanban-board artifacts to determine which slice to implement. Each slice
  crosses all layers (data → pure → edge → UI → integration), follows
  Red-Green-Refactor, passes an inner review, and ends in its own commit.
  Works from a plan, or in ad-hoc mode with no plan as a single reviewed slice.
  Clear context between slices. Use this skill whenever the user says
  "implement", "start coding", "proceed with implementation", "/implement", or
  wants to begin implementation.
  Entry point: /implement
---

# Implement Skill

Guides implementation one vertical slice at a time using the Kanban board artifact
as the source of truth. Each slice delivers something testable, crosses all layers,
passes an inner `reviewer` pass, and is committed on its own. TDD is built into the
loop (Red → Green → Refactor). The `impl-progress` artifact carries the state
between slices, so `/clear` never loses the resume point.

With no plan artifacts, it runs in **ad-hoc mode**: one goal, one acceptance
criterion, one reviewed commit. The baseline — tests, inner review, real commit —
is the same; only the plan and kanban are skipped.

---

## Gotchas

- Never skip the quality gate (Step 4). If the target language has no test framework or
  type checker, install or configure one before writing any production code.
- When exploring the module before the Red phase, read the relevant files directly. One focused exploration pass per slice.
- `impl-progress` is the resume point. A `/clear` after a `hitl` gate is recommended,
  not required; `afk` slices can chain in one session.
- Pull coding conventions from project AGENTS.md at the start of each slice (Step 4).
  Do NOT load them in Step 1 — only the slice's own conventions are needed.
- A slice's `mode` drives the gates: `hitl` (the default) stops for a go on the brief
  before the Red phase (Step 5) and for human review before the commit; `afk`
  may run unattended only when checks are green and the inner review found no Critical
  items, otherwise it degrades to a `hitl` gate.
- If the last slice completes, mark the artifact as complete and recommend `/review`.
- Bug fix = root cause, not symptom. Before editing, grep every caller of the function you
  touch. Fix the shared function once — one guard there is a smaller diff than one per caller,
  and patching only the path the ticket names leaves a sibling caller still broken.

---

## Step 1: Load Artifacts

Resolve the artifact label from the current branch name — the ticket key when the
branch carries one, otherwise the branch name with `/` replaced by `-`:

<!-- artifact-label:begin — shared verbatim across /plan, /implement, /review, /ship and @reviewer; make lint-agents checks identity -->
```bash
TICKET=$(git branch --show-current | grep -oE '[A-Z]+-[0-9]+' | head -1)
LABEL=${TICKET:-$(git branch --show-current | tr '/' '-')}
```
<!-- artifact-label:end -->

Read the plan artifact for full context:

```bash
cat .agents/artifacts/${LABEL}-plan.md 2>/dev/null
```

Read the Kanban board artifact for slice definitions:

```bash
cat .agents/artifacts/${LABEL}-kanban-board.md 2>/dev/null
```

**If either artifact is missing, enter [ad-hoc mode](#ad-hoc-mode-no-plan) instead of
stopping.** If both exist, also read the progress artifact, which is the resume point:

```bash
cat .agents/artifacts/${LABEL}-impl-progress.md 2>/dev/null
```

If found with `status: in_progress` — the first slice whose frontmatter `status`
is not `complete` (or the one marked `in_progress`) is the resume point. Announce:

> "Resuming implementation — Slices [N, M] are complete. Starting from Slice [K]."

Skip directly to Step 4 (Quality Gate).

If found with `status: complete` — warn:

> "Implementation appears already complete. Run `/review` to review the changes,
> or read the plan and progress artifacts for a full overview."

---

## Ad-hoc Mode (no plan)

For a quick fix with no `/plan` artifacts, run a single `hitl` slice through the
full loop. Take a one-sentence ticket from the branch label and ask for exactly two
things:

> "No plan artifacts found for `${LABEL}`. In one sentence, what is the goal? And
> what is the single acceptance criterion that proves it works?"

Then:

1. Skip Step 2 (there is no board to display) and Step 3's multi-slice template;
   write a one-row progress artifact instead — Step 3's schema with a single slice
   whose `title` is the goal, `status: in_progress`, `commit: null`.
2. Use the acceptance criterion where the loop would otherwise use the kanban's
   `module_interfaces`.
3. Run Steps 4–14 with slice `N = 1` and `mode: hitl`.

Ad-hoc mode skips only the plan and kanban artifacts. It never skips the quality
gate, TDD, the inner `reviewer` pass, or the per-slice commit.

---

## Step 2: Display the Kanban Board

Show the slice dependency graph to the user. The board carries no per-slice state —
`Status` comes from the impl-progress artifact:

```
## Kanban Board: <LABEL>

| Slice | Title | Blocks | Blocked By | Mode | Status |
|-------|-------|--------|------------|------|--------|
| 1     | ...   | [2]    | []         | hitl | pending |
| 2     | ...   | [3]    | [1]        | hitl | pending |
| 3     | ...   | []     | [2]        | afk  | pending |
```

Identify which slice(s) are unblocked (no blockers, or all blockers complete):

- **First unblocked slice:** Slice [N]
- **Parallel candidates:** Slices [M, O] can run in parallel when their
  `blocked_by` lists are satisfied

Ask the user which slice to start with:

> "The first unblocked slice is Slice [N]: [title]. Shall I start there, or skip to
> a different unblocked slice?"

---

## Step 3: Create Progress Artifact (first slice only)

If no progress artifact exists yet:

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

Write `.agents/artifacts/<LABEL>-impl-progress.md`. The frontmatter `slices:` list is
the state that Step 13 updates and Step 1 resumes from; the body table is
display-only:

```yaml
---
artifact: impl-progress
ticket: <LABEL>
skill: implement
status: in_progress
created: <ISO 8601 timestamp>
current_slice: <first slice id>
slices:
  - id: 1
    title: <title>
    status: pending
    commit: null
  - id: 2
    title: <title>
    status: pending
    commit: null
---

## Slice Progress

| Slice | Title | Mode | Status | Commit |
|-------|-------|------|--------|--------|
| 1 | <title> | hitl | pending | — |
| 2 | <title> | hitl | pending | — |
```

`status` values: `pending`, `in_progress`, `complete`, `skipped`.
`commit` is the slice's short sha once committed, and the `--fixup` target for
corrections (Step 12).

---

## Step 4: Quality Gate — Verify Test Infrastructure

Before writing any code for the current slice, verify the feedback loop infrastructure
for the target module's language and framework:

```bash
# Detect stack
FILES_CHANGED=<module files for this slice>

# Python
if echo "$FILES_CHANGED" | grep -q '\.py$'; then
  echo "=== Python checks ==="
  uv run pytest --collect-only -q 2>&1 | tail -5
  uv run ruff check . 2>&1 | tail -5
  uv run mypy . 2>&1 | tail -5
fi

# TypeScript/JavaScript
if echo "$FILES_CHANGED" | grep -qE '\.ts$|\.tsx$|\.js$'; then
  echo "=== TS/JS checks ==="
  npm test -- --passWithNoTests 2>&1 | tail -5
  npm run typecheck 2>&1 | tail -5
  npm run lint 2>&1 | tail -5
fi

# Ruby
if echo "$FILES_CHANGED" | grep -q '\.rb$'; then
  echo "=== Ruby checks ==="
  bundle exec rspec --dry-run 2>&1 | tail -5
  bundle exec rubocop 2>&1 | tail -5
fi
```

If any check fails because the tool is missing or not configured, install/configure it.
If any check fails for pre-existing reasons (not related to the current slice), note
them as deferred items and proceed.

**If tests exist for the module** — note the test framework and conventions:
```bash
# Show a sample test file for conventions
TEST_FILE=$(find . -path '*/test*' -name "*$(basename $(echo $FILES_CHANGED | head -1 | sed 's/\.py$//' | sed 's/\.ts$//'))*" 2>/dev/null | head -1)
[ -n "$TEST_FILE" ] && head -30 "$TEST_FILE"
```

**If no tests exist for the module** — this is the first TDD cycle for this area. Plan
to write the first test in Step 6.

### Pull Conventions

Load project-specific conventions that apply to this slice:

```bash
echo "=== Project conventions ==="
cat AGENTS.md 2>/dev/null | head -50
cat .agents/conventions.md 2>/dev/null
```

Extract only the rules relevant to the current slice's language and module type.

---

## Step 5: Explore the Module (before Red phase)

Before writing tests or code, read the relevant module files directly (see Gotchas —
one focused exploration pass per slice). Use the slice's `module_interfaces` list from
the Kanban board:

- Read each file listed under `module: <file path>`
- Search for existing test files that cover the module
- Note existing type definitions, function signatures, and conventions

### Slice Brief — `hitl` only

Before the Red phase of a `hitl` slice, describe what the slice will do and wait for
a go. `afk` slices skip the brief.

```
## Slice <N>: <title>   [mode: hitl]

- Goal: <what the slice delivers, one sentence>
- Steps: <ordered list — tests to write, files to change>
- Live or remote actions: <deploy, apply, SSH writes, cloud API calls — or "none">
- Checks: <the commands Step 9 will run>
```

> "That is the plan for Slice <N>. Go, or tell me what to adjust?"

**Do not write tests or code until the user says go.** A go on the brief covers the
local work only: confirm each live or remote action again right before running it.

---

## Step 6: RED — Write a Failing Test

Write a test that captures the slice's acceptance criterion. The test should fail
because the production code doesn't exist yet (or doesn't implement the behavior).
There is no confirmation prompt — capture the failing output as evidence for the
gate summary.

Rules:
- Write exactly one test (or a small group if the slice has multiple facets)
- The test must be runnable and deterministically fail
- Do NOT write any production code in this step
- Follow existing test conventions discovered in Step 4

Run it to confirm it fails:

```bash
# Python
uv run pytest <test_file> -k <test_name> -v 2>&1 | tail -15

# TypeScript/JavaScript
npx jest <test_file> --testNamePattern <test_name> 2>&1 | tail -15

# Ruby
bundle exec rspec <test_file> -e <test_name> 2>&1 | tail -15
```

Record the failing command and the one-line reason it failed for the gate summary.

---

## Step 7: GREEN — Implement Minimum Code

Write the minimum production code to pass the test. This crosses all layers relevant
to the slice — types, logic, edge code, and wiring — but only what's needed to make
the test pass.

Rules:
- Write the minimum code — no gold plating, no future-proofing
- Cross all layers for this slice (not just one stage)
- Integrate existing modules rather than rewriting them
- If the plan prescribes a specific implementation, follow it — but only implement
  enough to pass the test

Run the test again to confirm it passes:

```bash
# Python
uv run pytest <test_file> -k <test_name> -v 2>&1 | tail -15

# TypeScript/JavaScript
npx jest <test_file> --testNamePattern <test_name> 2>&1 | tail -15

# Ruby
bundle exec rspec <test_file> -e <test_name> 2>&1 | tail -15
```

If the test fails, iterate: fix the production code and re-run. If 3+ attempts fail,
stop and ask the user for guidance.

Record the passing command and count for the gate summary.

---

## Step 8: REFACTOR — Clean Up

With the test passing, refactor both test and production code:

1. Remove duplication
2. Improve naming
3. Align with project conventions from Step 4
4. Check for edge cases that should be tested

After refactoring, run the full suite to confirm no regressions:

```bash
# Run all tests (not just the new one) to check for regressions
# Python
uv run pytest 2>&1 | tail -10

# TypeScript/JavaScript
npx jest --passWithNoTests 2>&1 | tail -10

# Ruby
bundle exec rspec 2>&1 | tail -10
```

If any tests fail, revert the refactoring changes and try a more conservative approach.
Record what changed (or "none") for the gate summary.

---

## Step 9: Verify — Run Full Check Suite

Run the full verification suite for the project:

```bash
# Detect and run verification
make check 2>/dev/null || make test 2>/dev/null || echo "No check target found"
```

Report results:
- **All passing** — proceed to the inner review
- **Failures in new code** — fix and re-run
- **Pre-existing failures** — note as deferred items, proceed

---

## Step 10: Inner Review

Spawn the `reviewer` subagent on the current slice, before the gate:

> `@reviewer slice`

The reviewer diffs `git diff HEAD` plus untracked files — since the slice is not
committed yet, that is exactly this slice's work. It returns findings grouped by
severity and a `GATE:` line.

Fix every **Critical** and **Warning** finding, then re-run the Step 9 checks.

Cap the loop at **two review→fix rounds**. If a round still leaves Critical or Warning
items, stop, record the remainder in the gate summary, and continue. Nit items do not
require another round.

---

## Step 11: GATE — Slice Approval

Present the slice summary. For a `hitl` slice one approval covers both the review and
the commit:

```
## Slice <N>: <title>   [mode: hitl|afk]

### What was built
- [file 1]: <what was added/changed>
- [file 2]: <what was added/changed>

### Test evidence
- RED: `<test name>` — failed: <one-line reason>
- GREEN: <test command> — <N> passed
- REFACTOR: <what changed, or "none">
- Checks: lint <pass/fail> · types <pass/fail> · tests <N> passed>

### Inner review
- Rounds: <N>
- Fixed: <Critical/Warning items fixed, or "none">
- Leftovers: <anything not fixed, with reason; otherwise "none">

### Deviations
- [none / list of Rule N auto-fixes applied]

### Proposed commit
<LABEL>: <what this slice delivers>

<why this change is needed — the reasoning, context, or problem being solved.
Pull from the plan's context/rationale. Always present, even for a small change.>

Co-Authored-By: AI Assistant
```

Gate conditions:
- **`mode: hitl`** (the default) — stop and request approval:
  > "Slice <N> is `hitl` — review the summary and commit message; approve to commit, or tell me what to adjust."
- **`mode: afk`** — when checks are green and no Critical item remains, commit
  without waiting and continue to the next unblocked slice. Otherwise degrade to
  the `hitl` gate above.
- **No mode field** — treat it as `hitl` (default).

**Do not commit a `hitl` slice until the user approves.**

---

## Step 12: Commit the Slice

Stage the slice's files explicitly (never `git add -A`), then commit with the
approved message. The subject is the label resolved in Step 1:

```bash
git status
git add <files for this slice>
git commit -m "$(cat <<'EOF'
<LABEL>: <what this slice delivers>

<why this change is needed — the reasoning, context, or problem being solved.
Pull from the plan's context/rationale. Always present, even for a small change.>

Co-Authored-By: AI Assistant
EOF
)"
```

### Corrections to an earlier slice

If a later slice, the inner review, or the final `/review` corrects work from an
earlier slice, commit the correction as a fixup against that slice's commit sha
(recorded in `impl-progress`):

```bash
git commit --fixup=<slice sha>
```

`/ship` autosquashes fixups into their targets before pushing, so history stays one
commit per slice.

---

## Step 13: Update Progress Artifact

Record the slice's `status` and `commit` in the frontmatter and advance
`current_slice`. Use `--front-matter=process` so `yq` leaves the markdown body
alone, and `strenv()` because `yq` v4.53 has no `--arg` (plain `yq -i` fails on
the body's markdown):

```bash
PROGRESS_FILE=".agents/artifacts/${LABEL}-impl-progress.md"
COMMIT_SHA=$(git rev-parse --short HEAD)
export SLICE_ID=<N> NEW_STATUS=complete COMMIT_SHA
yq --front-matter=process -i '(.slices[] | select((.id | tostring) == strenv(SLICE_ID)) | .status) = strenv(NEW_STATUS)' "$PROGRESS_FILE"
yq --front-matter=process -i '(.slices[] | select((.id | tostring) == strenv(SLICE_ID)) | .commit) = strenv(COMMIT_SHA)' "$PROGRESS_FILE"

# Point current_slice at the next unblocked slice
export NEXT_SLICE=<id>
yq --front-matter=process -i '.current_slice = (strenv(NEXT_SLICE) | tonumber)' "$PROGRESS_FILE"
```

Keep the display-only body table in sync by hand. Verify the result:

```bash
cat .agents/artifacts/${LABEL}-impl-progress.md
```

Also update `.agents/STATE.md`:

```yaml
---
last_updated: <NOW>
current_branch: <BRANCH>
position: implement — slice <N> committed
---
## Decisions
- <decisions made during this slice>

## Blockers
- <if any>
```

---

## Step 14: Clear and Resume

If there are more slices to implement:

> "Slice <N> is committed. Run `/clear` to start fresh, then paste the prompt below."

End with a copy-pasteable handoff prompt for the next slice, in one fenced block:

```
/implement Slice <M>: <title>

Read first: <impl-progress, kanban, STATE.md, conventions.md, the slice's module files>
Scope: <what Slice <M> delivers, and what it must not touch>
Live state: <what is deployed or applied now, and anything changed by hand>
Carried-over deferrals: <open items from earlier slices that land in or affect Slice <M>>
Working rules: <the session's corrections and conventions that still apply>
Checks: <the commands Step 9 runs>
```

Fill it from `impl-progress`, `.agents/STATE.md` and `.agents/conventions.md`, plus what
this session learned that those files do not hold. The progress artifact remains the
resume point — `/implement` reads it in Step 1 — and the prompt carries the session
context it lacks. `afk` slices may continue in the same session without a clear or a
prompt.

---

## Step 15: All Slices Complete

When the last slice is done:

1. Set `status: complete` in the progress artifact frontmatter
2. Run the full verification suite one final time:

```bash
make check 2>/dev/null || make test 2>/dev/null
```

3. Update `.agents/STATE.md` with `position: complete`

Display completion message:

```
## Implementation Complete

Slices completed:
  ✅ Slice 1 — <title>
  ✅ Slice 2 — <title>
  ✅ Slice 3 — <title>

Checks: ✅ passing  (or: ⚠️  see failures above)

Next step: run /review for a severity-grouped code review against main.
```

Run `/clear` before `/review` to keep review context focused.

---

## Authentication Gate Protocol

Auth errors during execution are *gates*, not bugs. Indicators: "Not authenticated", "Not logged in", "Unauthorized", "401", "403", "Please run {tool} login", "Set {ENV_VAR}".

When encountered during any slice:
1. Recognize it's an auth gate, not a bug to auto-fix
2. STOP the current task immediately
3. Show the user exactly what command to run or credential to provide (e.g. `glab auth login`, `huggingface-cli login`, API key name)
4. Provide a verification command to confirm auth is working
5. Wait for user to complete the auth step before continuing

Document auth gates as "normal flow" in the slice gate summary, not as deviations.

---

## Deviation Rules

While executing a slice, you may discover work not explicitly in the plan. Apply these rules automatically. Track all deviations in the slice summary when presenting for gate approval.

**Auto-fix** (no permission needed):

| Rule | What | Examples |
|------|------|----------|
| 1 | Bugs in code you just wrote | Wrong queries, logic errors, type errors, null pointer exceptions, broken validation, security vulnerabilities, race conditions |
| 2 | Missing critical functionality | Error handling, input validation, null checks, auth on protected routes, missing DB indexes, no error logging |
| 3 | Blocking issues | Missing dependency, wrong types, broken imports, missing env var, circular dependency |

**Ask** (stop and get user decision):

| Rule | What | Examples |
|------|------|----------|
| 4 | Architectural changes | New DB table (not column), major schema changes, new service layer, switching libraries/frameworks, changing auth approach, new infrastructure, breaking API changes |

Fix inline → add/update tests if applicable → verify fix works → continue task. Document deviations in the slice gate summary using format: `[Rule N - Type] description`.

**Scope boundary:** Only auto-fix issues DIRECTLY caused by the current slice's changes. Pre-existing linting errors or failures in unrelated files are out of scope — log them to .agents/STATE.md as deferred items.

**Fix attempt limit:** After 3 auto-fix attempts on a single issue, stop fixing, document remaining issues in the summary as "Deferred Issues", and continue to the next slice.

---

## Quality Bar

A good implementation under this skill should:
- Follow TDD: RED → GREEN → REFACTOR, never write production code before a failing test
- Deliver each slice as a vertical cross-section — types, logic, edge, and wiring in one pass
- Keep slices small enough to review in one glance
- Pass the quality gate before writing code
- Pass the inner review and full verification before the gate
- Commit each slice on its own with a why body — git history is the record
- Pull conventions (don't push them) — keep implementer context lean
- Hand off via `impl-progress` and a handoff prompt, clearing context at `hitl` gates
