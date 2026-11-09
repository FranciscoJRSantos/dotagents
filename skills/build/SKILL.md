---
name: build
description: >
  Autonomous vertical-slice implementation. Reads plan.org and board.org from the
  work's .agents/artifacts/<slug>/ folder to determine which slice to implement.
  Each slice crosses all layers (data → pure → edge → UI → integration), follows
  Red-Green-Refactor, passes an inner review, and ends in its own commit. All
  slices run AFK — no per-slice human gates. The agent runs end-to-end autonomously.
  Works from a plan, or in ad-hoc mode with no plan as a single reviewed slice. Use
  this skill whenever the user says "implement", "start coding", "proceed with
  implementation", "@build", or wants to begin implementation.
  Entry point: @build [slug]
---

# Build Skill

Autonomous implementation one vertical slice at a time using the work's `board.org` as
the source of truth. Each slice delivers something testable, crosses all layers,
passes an inner `reviewer` pass, and is committed on its own. TDD is built into the
loop (Red → Green → Refactor). Each slice's Org TODO keyword (`TODO`, `DOING`,
`DONE`, `SKIPPED`) and its `:COMMIT:` property are the only state between slices, so
`/clear` never loses the resume point.

**All slices are AFK** — no per-slice human gates. The agent runs end-to-end,
committing each slice autonomously. The only HITL point is `@review` at the end,
where risk classification determines whether human review is needed.

With no work folder, it runs in **ad-hoc mode**: one goal, one acceptance
criterion, one reviewed commit. The baseline — tests, inner review, real commit —
is the same; only the plan is skipped.

---

## Conversation Density

**Conversation is routing only.** Keep conversation output to 1-3 lines per slice.
Write all detail to artifacts. The user reads conversation for decisions, drills into
artifacts for detail.

- Slice progress → artifact (board.org)
- TDD details → artifact
- Conversation: "Slice 1/N → commit abc1234 → next"

---

## Subagent Routing

This skill spawns a `reviewer` subagent (Step 10). The reviewer **must use a different model family** than the orchestrator — never review with the same model that implemented the code.

**Required:** Spawn the reviewer with explicit model:
```
model: opencode-go/glm-5.3-flash
```

This keeps review independent (different family = independent signal) and off the company quota. See global `AGENTS.md` → "Model routing" for the canonical table.

---

## Gotchas

- Never skip the quality gate (Step 4). If the target language has no test framework or
  type checker, install or configure one before writing any production code.
- When exploring the module before the Red phase, read the relevant files directly. One focused exploration pass per slice.
- `board.org` is the resume point. A `/clear` after a slice is recommended
  for context hygiene; AFK slices can chain in one session.
- Change `board.org` only with the `sed` blocks in Steps 3 and 13, never with the edit
  tool: every slice has an identical `:COMMIT:` line, and the `sed` range keeps the
  change inside one slice's drawer. Run `org-check` after every change.
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

## Step 1: Load the Work Folder

Each piece of work lives in `.agents/artifacts/<slug>/`. Resolve it with
`artifact-dir`, passing the slug when the invocation names one (`@build <slug>`)
and an empty string otherwise. It exits 1 on anything but a folder, so capture its
status and never run it under `set -e`:

```bash
SLUG=<slug from the invocation, or empty>
OUT=$(~/.agents/bin/artifact-dir "$SLUG"); rc=$?
echo "$OUT"
DIR=$(printf '%s\n' "$OUT" | sed -n 's/^ARTIFACT_DIR=//p')
```

- **`ARTIFACT_DIR=…`** (`rc` 0, possibly after `REOPENED: <slug>`) — read the board
  and the plan, then go to Step 2. An ad-hoc folder has no `plan.org`; the board's
  acceptance criterion stands in for it:

  ```bash
  cat "$DIR/board.org"
  [ -f "$DIR/plan.org" ] && cat "$DIR/plan.org"
  ```

  If the folder has no `board.org` (a grill log that was never planned), ask:
  > "`<slug>` has no `board.org`. Run `@arch <slug>` first, or continue in ad-hoc
  > mode in this folder?"
- **`NONE`** — there is no work at all: enter [ad-hoc mode](#ad-hoc-mode-no-plan).
- **`AMBIGUOUS: …`** or **`NOT FOUND: <slug>`** — show the output and ask which slug
  to use, then run the block again with it.

A `LEGACY LAYOUT` warning on stderr means flat files from the old layout are present;
they are ignored, so carry on.

---

## Ad-hoc Mode (no plan)

For a quick fix with no `@arch` artifacts, run a single slice through the
full loop. Ask for exactly two things:

> "No planned work found. In one sentence, what is the goal? And what is the single
> acceptance criterion that proves it works?"

Propose a folder name from the goal, and check it is not taken:

```bash
SLUG=$(~/.agents/bin/slug "<goal>")
for d in ".agents/artifacts/$SLUG" ".agents/archive/$SLUG"; do
  [ -e "$d" ] && echo "EXISTS: $d"
done
echo "$SLUG"
```

> "I'll keep this work in `.agents/artifacts/<slug>/`. OK, or another name?"

On `EXISTS`, ask for another name. When Step 1 resolved a folder without
`board.org`, skip the proposal and use that folder's slug. Then make sure `.agents/`
ignores its own state:

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

Write a one-slice `board.org` — the `@arch` board template with the acceptance
criterion where the module interfaces would go — and check it:

```bash
SLUG=<the confirmed slug>
DIR=".agents/artifacts/$SLUG"
mkdir -p "$DIR"
cat > "$DIR/board.org" <<'EOF'
#+TITLE: Board: <goal>
#+CREATED: <ISO 8601 timestamp, UTC>
#+TODO: TODO DOING | DONE SKIPPED

* TODO Slice 1: <goal>
:PROPERTIES:
:SLICE: 1
:MODE: afk
:BLOCKS:
:BLOCKED_BY:
:COMMIT:
:END:
<goal>

** Acceptance criterion
- <the acceptance criterion>
EOF
~/.agents/bin/org-check "$DIR/board.org"
```

Write Org markup in the placeholders (`=path=`, `~code~`), never backticks. Then:

1. Skip Step 2 — the board has one slice.
2. Sync the board to `todowrite` via [Visual Progress Sync](#visual-progress-sync) — one slice, status `pending`.
3. Use the acceptance criterion where the loop would otherwise use the slice's
   module interfaces.
4. Run Steps 3–14 with slice `N = 1` and `mode: afk`.

Ad-hoc mode skips only the plan. It never skips the quality gate, TDD, the inner
`reviewer` pass, or the per-slice commit.

---

## Step 2: Display the Board and Pick the Slice

List every slice with its keyword, mode, blockers and commit, and derive the resume
point: the first `DOING` slice, else the first `TODO` slice whose `:BLOCKED_BY:`
slices are all `DONE`. `READY:` lists every unblocked `TODO` slice (parallel
candidates):

```bash
awk '
  /^\* [A-Z]+ Slice [0-9]+:/ {
    n++; kw[n] = $2; id[n] = $4; sub(/:$/, "", id[n]); state[id[n]] = $2
    t = $0; sub(/^\* [A-Z]+ Slice [0-9]+: */, "", t); title[n] = t
    mode[n] = "afk"; bb[n] = ""; sha[n] = ""; drawer = 0; next
  }
  n && /^:PROPERTIES:$/ { drawer = 1; next }
  /^:END:$/ { drawer = 0; next }
  drawer && $1 == ":MODE:" { mode[n] = $2 }
  drawer && $1 == ":BLOCKED_BY:" { $1 = ""; bb[n] = substr($0, 2) }
  drawer && $1 == ":COMMIT:" { sha[n] = $2 }
  END {
    for (i = 1; i <= n; i++) {
      printf "%-3s %-7s %-4s blocked_by: %-6s commit: %-8s %s\n", id[i], kw[i], mode[i],
        (bb[i] == "" ? "-" : bb[i]), (sha[i] == "" ? "-" : sha[i]), title[i]
      if (kw[i] == "DOING" && doing == "") doing = id[i]
      if (kw[i] == "TODO") {
        todo = 1; ok = 1; k = split(bb[i], b, " ")
        for (j = 1; j <= k; j++) if (state[b[j]] != "DONE") ok = 0
        if (ok) ready = ready " " id[i]
      }
    }
    split(ready, r, " ")
    if (doing != "") print "NEXT: " doing " (DOING — resume)"
    else if (ready != "") print "NEXT: " r[1]
    else if (todo) print "NEXT: none — every TODO slice is blocked"
    else print "NEXT: none — every slice is DONE or SKIPPED"
    if (ready != "") print "READY:" ready
  }
' "$DIR/board.org"
```

Then sync the board state to OpenCode's visual progress via [Visual Progress Sync](#visual-progress-sync).

Show the listing to the user, then act on `NEXT:`:

- **`DOING — resume`** — announce and skip directly to Step 4:
  > "Resuming implementation — Slices [N, M] are DONE. Resuming Slice [K]."
- **A slice number** — ask:
  > "The first unblocked slice is Slice [N]: [title]. Shall I start there, or skip to
  > another slice in `READY:`?"
- **`every TODO slice is blocked`** — a blocker is `SKIPPED` or never finished; only
  `DONE` unblocks. Show the blockers and ask how to proceed.
- **`every slice is DONE or SKIPPED`** — warn:
  > "Implementation appears already complete. Run `@review` to review the changes,
  > or read `plan.org` and `board.org` for a full overview."

## Visual Progress Sync

After reading the board state, sync it to OpenCode's built-in `todowrite` tool for visual progress in the UI. This is a one-way sync: `board.org` remains the persistent, version-controlled source of truth; `todowrite` provides ephemeral visual feedback during the session.

Map each slice's Org keyword to a todowrite status:
- `TODO` → `pending`
- `DOING` → `in_progress`
- `DONE` → `completed`
- `SKIPPED` → `cancelled`

Call `todowrite` with the slice list:

```javascript
await tools.todowrite({
  todos: [
    { content: "Slice 1: Shared scripts", status: "completed" },
    { content: "Slice 2: @spec/@arch write Org", status: "in_progress" },
    { content: "Slice 3: @build uses board.org", status: "pending" }
  ]
});
```

The slice titles come from the `* TODO Slice N: <title>` headings in `board.org`. Parse them from the Step 2 awk output you already see.

This sync runs:
- After Step 2 (initial board display)
- After Step 12 (each slice marked DONE)

`board.org` is the source of truth. If `todowrite` fails or is unavailable, continue — the board state is what matters.

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
    # Read blocked_by from board.org for this slice
    BLOCKED_BY=$(awk -v n="$SLICE_ID" '
      /^\* [A-Z]+ Slice [0-9]+:/ { in_slice = ($4 == n":"); next }
      in_slice && /^:BLOCKED_BY:/ { $1=""; gsub(/^ +/,"",$0); print; exit }
    ' "$DIR/board.org")
    BLOCKED_BY_COUNT=$(echo "$BLOCKED_BY" | awk '{print NF}')
    
    if [ "$BLOCKED_BY_COUNT" -eq 0 ]; then
      # No dependencies: branch from epic
      git checkout -b "$SLICE_BRANCH" "$EPIC_BRANCH"
      echo "Created slice branch: $SLICE_BRANCH (from $EPIC_BRANCH)"
    elif [ "$BLOCKED_BY_COUNT" -eq 1 ]; then
      # Single dependency: branch from parent slice's branch
      PARENT_SLICE=$(echo "$BLOCKED_BY" | awk '{print $1}')
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

## Step 3: Mark the Slice DOING

Set the chosen slice's keyword to `DOING`. The pattern ends in `Slice $N:`, so
Slice 1 never matches Slice 10:

```bash
BOARD="$DIR/board.org"
N=<slice number>
sed -i "s/^\* [A-Z]* Slice $N:/* DOING Slice $N:/" "$BOARD"
~/.agents/bin/org-check "$BOARD" && grep "^\* [A-Z]* Slice $N:" "$BOARD"
```

The output must show `* DOING Slice <N>:`; `org-check` must pass before you continue.

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
approved message. The subject is the slice title from `board.org`:

```bash
git status
git add <files for this slice>
git commit -m "$(cat <<'EOF'
<slice title>

<why this change is needed — the reasoning, context, or problem being solved.
Pull from the plan's context/rationale. Always present, even for a small change.>

Co-Authored-By: AI Assistant
EOF
)"
```

### Corrections to an earlier slice

If a later slice, the inner review, or the final `@review` corrects work from an
earlier slice, commit the correction as a fixup against that slice's commit sha
(recorded in `board.org` under `:COMMIT:` for the relevant slice):

```bash
git commit --fixup=<slice sha>
```

If `:COMMIT:` is empty, the slice was never committed — ask which commit to target.
`@ship` autosquashes fixups into their targets before pushing, so history stays one
commit per slice.

---

## Step 12: Update the Board and STATE.org

Mark the slice `DONE` and record its commit. The second `sed` is scoped to the
range from the slice's heading to the end of its drawer, so it changes only that
slice's `:COMMIT:` line:

```bash
BOARD="$DIR/board.org"
N=<slice number>
SHA=$(git rev-parse --short HEAD)
sed -i "s/^\* [A-Z]* Slice $N:/* DONE Slice $N:/" "$BOARD"
sed -i "/^\* [A-Z]* Slice $N:/,/^:END:/ s/^:COMMIT:.*/:COMMIT: $SHA/" "$BOARD"
~/.agents/bin/org-check "$BOARD" && sed -n "/^\* [A-Z]* Slice $N:/,/^:END:/p" "$BOARD"
```

The output must show `* DONE Slice <N>:` and `:COMMIT: <sha>`. A slice the user
drops is marked the same way with `SKIPPED` and no commit (first `sed` only).

Then update `.agents/STATE.org`, the repo-wide state, with `POSITION` set to where
the work stands — for example `build — slice 3 committed (abc1234)`. The block rewrites the keyword
header — keeping `#+CREATED:` and everything below the header — and creates the file
with empty `* Decisions` and `* Blockers` sections when it is missing:

```bash
STATE=.agents/STATE.org
POSITION=<position>
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

Add the slice's decisions under `* Decisions` and any blockers under `* Blockers`,
one `- <YYYY-MM-DD> — <text>` item each, in Org markup (`=path=`, `~code~`, never
backticks). Run `org-check "$STATE"` again; it must pass.

Then sync the updated board state to `todowrite` via [Visual Progress Sync](#visual-progress-sync), so the UI reflects the slice now being DONE.

---

## Step 13: Continue to Next Slice

Run the Step 2 block again to read the next slice from the board. If it reports
one (`NEXT: <M>`):

For certified projects, return to the epic branch before creating the next slice's branch:

```bash
if [ "$PROJECT_TYPE" = "CERTIFIED_PROJECT" ]; then
  # Derive epic branch deterministically (handles resume after /clear)
  CURRENT_BRANCH=$(git branch --show-current)
  EPIC_BRANCH=$(echo "$CURRENT_BRANCH" | sed -E 's/-s[0-9]+$//')
  git checkout "$EPIC_BRANCH"
fi
```

> "Slice <N> is committed. Moving to Slice <M>."

No context clear or handoff prompt needed — all slices are AFK.

---

## Step 14: All Slices Complete

When the Step 2 block reports `every slice is DONE or SKIPPED` — the board needs no
further change:

1. Sync the final board state to `todowrite` via [Visual Progress Sync](#visual-progress-sync) — all slices should now be `completed` or `cancelled`.

2. Run the full verification suite one final time:

```bash
make check 2>/dev/null || make test 2>/dev/null || echo "No check target found"
```

2. Update `.agents/STATE.org` with the Step 12 block, `POSITION` set to `build — complete`

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

Run `/clear` before `@review` to keep review context focused.

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

**Scope boundary:** Only auto-fix issues DIRECTLY caused by the current slice's changes. Pre-existing linting errors or failures in unrelated files are out of scope — log them to .agents/STATE.org as deferred items.

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
