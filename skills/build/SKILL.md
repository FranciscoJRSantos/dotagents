---
name: build
description: >
  Autonomous vertical-slice implementation. Reads the plan and kanban-board
  artifacts to determine which slice to implement. Each slice crosses all layers
  (data → pure → edge → UI → integration), follows Red-Green-Refactor, passes
  an inner review, and ends in its own commit. All slices run AFK — no per-slice
  human gates. The agent runs end-to-end autonomously. Works from a plan, or in
  ad-hoc mode with no plan as a single reviewed slice. Use this skill whenever
  the user says "implement", "start coding", "proceed with implementation",
  "@build", or wants to begin implementation.
  Entry point: @build
---

# Build Skill

Autonomous implementation one vertical slice at a time using the Kanban board artifact
as the source of truth. Each slice delivers something testable, crosses all layers,
passes an inner `reviewer` pass, and is committed on its own. TDD is built into the
loop (Red → Green → Refactor).

**All slices are AFK** — no per-slice human gates. The agent runs end-to-end,
committing each slice autonomously. The only HITL point is `@review` at the end,
where risk classification determines whether human review is needed.

With no plan artifacts, it runs in **ad-hoc mode**: one goal, one acceptance
criterion, one reviewed commit. The baseline — tests, inner review, real commit —
is the same; only the plan and kanban are skipped.

---

## Conversation Density

**Conversation is routing only.** Keep conversation output to 1-3 lines per slice.
Write all detail to artifacts. The user reads conversation for decisions, drills into
artifacts for detail.

- Slice progress → artifact (board.org)
- TDD details → artifact
- Conversation: "Slice 1/N → commit abc1234 → next"

---

## Gotchas

- Never skip the quality gate (Step 4). If the target language has no test framework or
  type checker, install or configure one before writing any production code.
- When exploring the module before the Red phase, read the relevant files directly. One focused exploration pass per slice.
- `impl-progress` is the resume point. A `/clear` after a slice is recommended
  for context hygiene; AFK slices can chain in one session.
- Pull coding conventions from project AGENTS.md at the start of each slice (Step 4).
  Do NOT load them in Step 1 — only the slice's own conventions are needed.
- **All slices are AFK** — the agent runs end-to-end without stopping. Inner reviewer
  runs, checks run, commit happens, move to next slice. The only stop is `@review`
  at the end, where risk classification determines escalation.
- If the last slice completes, mark the artifact as complete and recommend `@review`.
- Bug fix = root cause, not symptom. Before editing, grep every caller of the function you
  touch. Fix the shared function once — one guard there is a smaller diff than one per caller,
  and patching only the path the ticket names leaves a sibling caller still broken.

---

## Step 1: Load Artifacts

Resolve the artifact label from the current branch name — the ticket key when the
branch carries one, otherwise the branch name with `/` replaced by `-`:

<!-- artifact-label:begin — shared verbatim across @arch, @build, @review, @ship and @reviewer; make lint-agents checks identity -->
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

For certified projects, run Step 2a (Create Slice Branch) before Step 4 to ensure
the correct slice branch is checked out. Then skip directly to Step 4 (Quality Gate).

If found with `status: complete` — warn:

> "Implementation appears already complete. Run `@review` to review the changes,
> or read the plan and progress artifacts for a full overview."

---

## Ad-hoc Mode (no plan)

For a quick fix with no `@arch` artifacts, run a single slice through the
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
3. Run Steps 4–14 with slice `N = 1`.

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
| 1     | ...   | [2]    | []         | afk  | pending |
| 2     | ...   | [3]    | [1]        | afk  | pending |
| 3     | ...   | []     | [2]        | afk  | pending |
```

Identify which slice(s) are unblocked (no blockers, or all blockers complete):

- **First unblocked slice:** Slice [N]
- **Parallel candidates:** Slices [M, O] can run in parallel when their
  `blocked_by` lists are satisfied

Start with the first unblocked slice. All slices are AFK — proceed autonomously.

### 2a: Create Slice Branch (certified projects only)

For certified projects, each slice gets its own branch based on the dependency graph:

```bash
# Set SLICE_ID from Step 2 (first unblocked slice)
# SLICE_ID=<first unblocked slice id from Step 2>

# Detect certified project — shared snippet with @ship
<!-- project-config-detection:begin — shared verbatim across @ship (2 copies) and @build -->
# Detect certified project — three states: CERTIFIED / STANDARD / UNPARSEABLE
# Only literal true/True/TRUE count as certified; false/False/FALSE are standard;
# anything else (quoted strings, yes, on, 1) exits 1 to prevent silent fallback
if [ -f ".agents/project.yaml" ]; then
  if grep -qE '^certified:[[:space:]]*(true|True|TRUE)[[:space:]]*(#.*)?$' .agents/project.yaml; then
    PROJECT_TYPE="CERTIFIED_PROJECT"
  elif grep -qE '^certified:[[:space:]]*(false|False|FALSE)[[:space:]]*(#.*)?$' .agents/project.yaml; then
    PROJECT_TYPE="STANDARD_PROJECT"
  elif grep -qE '^certified:[[:space:]]' .agents/project.yaml; then
    LINE=$(grep -E '^certified:' .agents/project.yaml | head -1)
    echo "Error: .agents/project.yaml has certified line but value not recognized:" >&2
    echo "  $LINE" >&2
    echo "Only literal true/True/TRUE or false/False/FALSE accepted (no quotes, no 'yes'/'on')." >&2
    exit 1
  else
    PROJECT_TYPE="STANDARD_PROJECT"
  fi
else
  PROJECT_TYPE="STANDARD_PROJECT"
fi
<!-- project-config-detection:end -->

if [ "$PROJECT_TYPE" = "CERTIFIED_PROJECT" ]; then
  # Derive epic branch by stripping -s<N> suffix (handles resume after /clear)
  CURRENT_BRANCH=$(git branch --show-current)
  EPIC_BRANCH=$(echo "$CURRENT_BRANCH" | sed -E 's/-s[0-9]+$//')
  
  # Verify we're on a valid branch (epic or slice branch)
  if [ "$CURRENT_BRANCH" = "$EPIC_BRANCH" ] || echo "$CURRENT_BRANCH" | grep -qE "^${EPIC_BRANCH}-s[0-9]+$"; then
    : # OK
  else
    echo "Error: current branch $CURRENT_BRANCH doesn't match expected pattern"
    echo "Expected: $EPIC_BRANCH or ${EPIC_BRANCH}-s<N>"
    exit 1
  fi
  
  SLICE_BRANCH="${EPIC_BRANCH}-s${SLICE_ID}"
  
  # Check if branch already exists (recovery scenario)
  if git show-ref --verify --quiet "refs/heads/$SLICE_BRANCH"; then
    echo "Branch $SLICE_BRANCH already exists — switching to it"
    git checkout "$SLICE_BRANCH"
  else
    # Determine parent branch from dependency graph
    # Read blocked_by from kanban board for this slice
    BLOCKED_BY_COUNT=$(yq --front-matter=process eval ".slices[] | select(.id == ${SLICE_ID}) | .blocked_by | length" .agents/artifacts/${LABEL}-kanban-board.md | head -1)
    
    if [ "$BLOCKED_BY_COUNT" -eq 0 ]; then
      # No dependencies: branch from epic
      git checkout -b "$SLICE_BRANCH" "$EPIC_BRANCH"
      echo "Created slice branch: $SLICE_BRANCH (from $EPIC_BRANCH)"
    elif [ "$BLOCKED_BY_COUNT" -eq 1 ]; then
      # Single dependency: branch from parent slice's branch
      PARENT_SLICE=$(yq --front-matter=process eval ".slices[] | select(.id == ${SLICE_ID}) | .blocked_by[0]" .agents/artifacts/${LABEL}-kanban-board.md | head -1)
      PARENT_BRANCH="${EPIC_BRANCH}-s${PARENT_SLICE}"
      
      if ! git show-ref --verify --quiet "refs/heads/$PARENT_BRANCH"; then
        echo "Error: parent branch $PARENT_BRANCH doesn't exist"
        echo "Slice $PARENT_SLICE must be implemented first"
        exit 1
      fi
      
      git checkout -b "$SLICE_BRANCH" "$PARENT_BRANCH"
      echo "Created slice branch: $SLICE_BRANCH (from $PARENT_BRANCH)"
    else
      # Multiple dependencies: not supported in certified mode
      echo "Error: certified projects require linear dependency chains"
      echo "Slice $SLICE_ID has $BLOCKED_BY_COUNT dependencies — only 0 or 1 supported"
      echo "Multi-dependency slices require merge-based workflow (not yet implemented)"
      exit 1
    fi
  fi
fi
```

For non-certified projects, continue on the current branch.

**Resume path:** If resuming after `/clear` or a crash, Step 2a runs before Step 4 (Quality Gate) to ensure the correct slice branch is checked out. The epic branch is derived deterministically from the current branch name.

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
skill: build
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
| 1 | <title> | afk | pending | — |
| 2 | <title> | afk | pending | — |
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

No brief gate — proceed directly to RED phase.

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

Spawn the `reviewer` subagent on the current slice, before the commit:

> `@reviewer slice`

The reviewer diffs `git diff HEAD` plus untracked files — since the slice is not
committed yet, that is exactly this slice's work. It returns findings grouped by
severity and a `GATE:` line.

Fix every **Critical** and **Warning** finding, then re-run the Step 9 checks.

Cap the loop at **two review→fix rounds**. If a round still leaves Critical or Warning
items, stop, record the remainder in the gate summary, and continue. Nit items do not
require another round.

---

## Step 11: Commit the Slice

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

If a later slice, the inner review, or the final `@review` corrects work from an
earlier slice, commit the correction as a fixup against that slice's commit sha
(recorded in `impl-progress`):

```bash
git commit --fixup=<slice sha>
```

`@ship` autosquashes fixups into their targets before pushing, so history stays one
commit per slice.

---

## Step 12: Update Progress Artifact

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
position: build — slice <N> committed
---
## Decisions
- <decisions made during this slice>

## Blockers
- <if any>
```

---

## Step 13: Continue to Next Slice

If there are more slices to implement, proceed to the next unblocked slice.
No context clear or handoff prompt needed — all slices are AFK.

For certified projects, return to the epic branch before creating the next slice's branch:

```bash
if [ "$PROJECT_TYPE" = "CERTIFIED_PROJECT" ]; then
  # Derive epic branch deterministically (handles resume after /clear)
  CURRENT_BRANCH=$(git branch --show-current)
  EPIC_BRANCH=$(echo "$CURRENT_BRANCH" | sed -E 's/-s[0-9]+$//')
  git checkout "$EPIC_BRANCH"
fi
```

> "Slice <N> committed. Moving to Slice <M>."

---

## Step 14: All Slices Complete

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

Next step: run @review for a risk-routed code review.
```

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

While executing a slice, you may discover work not explicitly in the plan. Apply these rules automatically. Track all deviations in the slice summary.

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

Fix inline → add/update tests if applicable → verify fix works → continue task. Document deviations in the slice summary using format: `[Rule N - Type] description`.

**Scope boundary:** Only auto-fix issues DIRECTLY caused by the current slice's changes. Pre-existing linting errors or failures in unrelated files are out of scope — log them to .agents/STATE.md as deferred items.

**Fix attempt limit:** After 3 auto-fix attempts on a single issue, stop fixing, document remaining issues in the summary as "Deferred Issues", and continue to the next slice.

---

## Quality Bar

A good implementation under this skill should:
- Follow TDD: RED → GREEN → REFACTOR, never write production code before a failing test
- Deliver each slice as a vertical cross-section — types, logic, edge, and wiring in one pass
- Keep slices small enough to review in one glance
- Pass the quality gate before writing code
- Pass the inner review and full verification before commit
- Commit each slice on its own with a why body — git history is the record
- Pull conventions (don't push them) — keep implementer context lean
- **Run autonomously end-to-end** — no per-slice human gates, only `@review` at the end
