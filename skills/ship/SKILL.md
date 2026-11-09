---
name: ship
description: >
  Run the full verification suite (lint, type check, tests), gate on a fresh
  review artifact, autosquash fixups, push, and create a merge request. Use this
  skill whenever the user says "ship it", "commit and push", "create MR", "open a
  merge request", "push my branch", or wants to finalize and submit their work.
---

# Ship Skill

Run the full check suite, gate on a review that matches HEAD, autosquash fixups,
push the branch, and create a merge request. Artifacts close last, so an aborted
ship never leaves them marked closed. `@ship` does not commit — `@build`
owns per-slice commits (including ad-hoc mode).

---

## Gotchas

- If MR creation fails because one already exists for the branch (`glab mr create` / `gh pr create`), view it instead of creating a duplicate (`glab mr view` / `gh pr view`) and show the URL to the user.
- Detect the forge from the `origin` remote before creating an MR — use `gh` for GitHub and `glab` for GitLab. If the matching CLI is missing, report it rather than failing the whole ship.
- Never use `--no-verify` to bypass a failing pre-commit hook. Fix the underlying issue instead.
- `@ship` never commits. If the working tree is dirty, stop and send the user to `@build` (ad-hoc mode) or a manual commit — do not stage or commit here.
- If the branch has no upstream yet, `git push -u origin <BRANCH>` sets it automatically — no separate `git push --set-upstream` needed.
- The `--target-branch` for the MR is detected from the branch's actual creation point (merge-base), falling back to git-flow naming conventions — never hardcode `main`.
- If `make type_check` exits 0 but printed type errors to stderr, the Makefile may be suppressing the exit code — check the output text for error patterns, not just the exit code.
- If a check command is missing (e.g. `make type_check` target not defined), report it as SKIPPED rather than FAIL — the target may simply not exist for this project.

---

## Certified Project Detection

Some projects require per-slice merge requests for compliance (e.g. HITRUST E1
certification). Detect this by checking for `.agents/project.yaml` with a
`certified: true` flag:

<!-- project-config-detection:begin — shared verbatim across @ship and @build -->
```bash
# Detect certified project — three states: CERTIFIED / STANDARD / UNPARSEABLE
# Only literal true/True/TRUE count as certified; false/False/FALSE are standard;
# anything else (quoted strings, yes, on, 1) exits 1 to prevent silent fallback
if [ -f ".agents/project.yaml" ]; then
  if grep -qE '^certified:[[:space:]]*(true|True|TRUE)[[:space:]]*(#.*)?$' .agents/project.yaml; then
    echo "CERTIFIED_PROJECT"
  elif grep -qE '^certified:[[:space:]]*(false|False|FALSE)[[:space:]]*(#.*)?$' .agents/project.yaml; then
    echo "STANDARD_PROJECT"
  elif grep -qE '^certified:[[:space:]]' .agents/project.yaml; then
    LINE=$(grep -E '^certified:' .agents/project.yaml | head -1)
    echo "Error: .agents/project.yaml has certified line but value not recognized:" >&2
    echo "  $LINE" >&2
    echo "Only literal true/True/TRUE or false/False/FALSE accepted (no quotes, no 'yes'/'on')." >&2
    exit 1
  else
    echo "STANDARD_PROJECT"
  fi
else
  echo "STANDARD_PROJECT"
fi
```
<!-- project-config-detection:end -->

Use this to adjust behavior: certified projects get per-slice MRs, standard
projects get a single MR at the end.

---

## Step 1: Run Verification Suite

Detect the project stack and run lint → type check → tests before anything else.

### 1a. Confirm a Clean Working Tree

`@ship` does not commit, so the tree must be clean first:

```bash
git status --porcelain
```

If anything is printed (other than `.agents/` state files, which are untracked
working state), stop:

> "The working tree is dirty. Commit the work first — `@build` in ad-hoc mode
> does this — or commit by hand, then run `@ship` again."

### 1b. Detect Makefile Targets

```bash
grep -E '^[a-zA-Z_-]+:' Makefile 2>/dev/null | cut -d: -f1 | sort
```

**If a `precommit` target exists**, run it directly and skip to Step 1d:

```bash
make precommit
```

### 1c. Detect Stack and Run Checks

If no `precommit` Make target, detect the stack:

| Check                                                 | Stack           |
|-------------------------------------------------------|-----------------|
| `pyproject.toml` with `[tool.uv]` or `uv.lock` exists | uv (Python)     |
| `pyproject.toml` with `[tool.poetry]` exists          | Poetry (Python) |
| `Gemfile` exists                                      | Ruby            |
| `package.json` exists (no Python files)               | Node.js         |

Run each step sequentially. Stop at first failure only if the failure is blocking
(e.g., import errors break type checking too).

**uv + ruff + ty:**
```bash
make lint
make type_check
make test
make nb_check 2>/dev/null
```

**uv + ruff, no ty:**
```bash
make lint
uv run pytest tests/ -v
```

**Poetry:**
```bash
poetry run flake8 .
poetry run pytest
```

**Ruby:**
```bash
make rubocop 2>/dev/null || docker compose exec web rubocop
make rspec 2>/dev/null || docker compose exec web bundle exec rspec
```

**Node.js:**
```bash
npm run lint
npm test
```

### 1d. Report Check Results

```
## Check Results

| Check       | Result | Details                  |
|-------------|--------|--------------------------|
| Lint        | PASS   |                          |
| Type check  | FAIL   | 3 errors (see below)     |
| Tests       | PASS   | 112 passed, 0 failed     |
```

**On failure:** show the first 3-5 errors with file and line number. Stop and let
the user fix before proceeding. Do not ship broken code.

**On full pass:** proceed to Step 2.

---

## Step 2: Gate — Review Freshness

Resolve the label and read the review artifact:

<!-- artifact-label:begin — shared verbatim across @arch, @build, @review, @ship and @reviewer; make lint-agents checks identity -->
```bash
TICKET=$(git branch --show-current | grep -oE '[A-Z]+-[0-9]+' | head -1)
LABEL=${TICKET:-$(git branch --show-current | tr '/' '-')}
```
<!-- artifact-label:end -->

```bash
REVIEW_FILE=".agents/artifacts/${LABEL}-review-impl.md"
cat "$REVIEW_FILE" 2>/dev/null
```

`@review` records the commit it reviewed as `reviewed_head` in the artifact
frontmatter. Compare it with the current HEAD before deciding:

```bash
HEAD_SHA=$(git rev-parse HEAD)
REVIEWED_HEAD=$(yq --front-matter=extract '.reviewed_head // ""' "$REVIEW_FILE" 2>/dev/null)

if [ ! -f "$REVIEW_FILE" ]; then
  echo "NO_REVIEW"
elif [ -z "$REVIEWED_HEAD" ]; then
  echo "NO_HEAD"                 # reviewed before this field existed
elif [ "$HEAD_SHA" = "$REVIEWED_HEAD" ]; then
  echo "FRESH"
elif ! git merge-base --is-ancestor "$REVIEWED_HEAD" HEAD 2>/dev/null; then
  echo "STALE"                   # history was rewritten since the review
elif [ "$(git log --format='%s' "$REVIEWED_HEAD"..HEAD | grep -vc '^fixup!')" -eq 0 ]; then
  echo "FIXUPS_ONLY"
else
  echo "STALE"
fi
```

Act on the result:

- **FRESH** — proceed.
- **FIXUPS_ONLY** — show the commits since `reviewed_head` (they are all `fixup!`
  corrections to already-reviewed slices), then proceed.
- **STALE** — show the commits since `reviewed_head` and ask: re-run `@review` on
  the new work, or proceed anyway because the changes are pre-approved.
- **NO_HEAD** — the artifact predates freshness tracking. Treat it like STALE and
  ask.
- **NO_REVIEW** — soft gate:

  > "No final review for this branch. Ship anyway?"

  Proceed only on an explicit yes.

Independently, if the artifact has `status: has-findings`, show the Critical and
Warning items and ask the user to confirm before proceeding.

---

## Step 3: Autosquash Fixups

Fold `--fixup` commits into their target slices so history reads one commit per
slice. This runs before the push, and is skipped when the branch already has an
upstream carrying these commits — rewriting pushed history would need a
force-push, which `@ship` never does silently.

```bash
BRANCH=$(git branch --show-current)

if git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
  echo "Branch has an upstream — skipping autosquash (pushed history is left alone)."
else
  BASE=$(git merge-base main HEAD 2>/dev/null \
    || git merge-base origin/main HEAD 2>/dev/null \
    || git merge-base master HEAD 2>/dev/null)
  GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash "$BASE"
fi
```

The freshness check in Step 2 runs first because the rebase rewrites the shas.

---

## Step 4: Push

```bash
git push -u origin <BRANCH>
```

---

## Step 5: Create Merge Request

### 5a. Detect the Forge

```bash
REMOTE_URL=$(git remote get-url origin 2>/dev/null)
case "$REMOTE_URL" in
  *github.com*) FORGE=github ;;
  *gitlab*)     FORGE=gitlab ;;
  *)            FORGE=unknown ;;
esac
echo "Forge: ${FORGE}"
```

### 5b. Detect the Target Branch

Detect the branch this one was actually cut from — never hardcode a default:

```bash
BRANCH=$(git branch --show-current)
TARGET_BRANCH=""

# 1. Find the actual parent branch by merge-base recency. The parent branch's
#    tip is the most recent common ancestor: the smallest number of commits
#    between the merge-base and HEAD wins. On a tie — e.g. main was
#    fast-forwarded to a merged feature branch's tip, so both share the same
#    merge-base — prefer the trunk branch by name; a plain lexicographic sort
#    would otherwise pick the stale, already-merged feature branch.
TARGET_BRANCH=$(
  for candidate in $(git branch --format='%(refname:short)' | grep -v "^${BRANCH}$"); do
    base=$(git merge-base HEAD "$candidate" 2>/dev/null) || continue
    [ -z "$base" ] && continue
    case "$candidate" in
      main|master|trunk) rank=0 ;;
      develop) rank=1 ;;
      *) rank=2 ;;
    esac
    echo "$(git rev-list --count "$base"..HEAD) $rank $candidate"
  done | sort -n -k1,1 -k2,2 | head -1 | awk '{print $3}'
)

# 2. Fall back to git-flow naming conventions if detection failed.
if [ -z "$TARGET_BRANCH" ]; then
  if [[ "$BRANCH" =~ ^(release|hotfix)/ ]]; then
    TARGET_BRANCH="main"
  elif [[ "$BRANCH" =~ ^(feature|feat|bugfix|fix|chore)/ ]] && git show-ref --verify --quiet refs/heads/develop; then
    TARGET_BRANCH="develop"
  else
    TARGET_BRANCH=$(git remote show origin | grep 'HEAD branch' | awk '{print $NF}')
  fi
fi

echo "Target branch: ${TARGET_BRANCH}"
```

Show the detected target branch to the user and let them override before creating
the MR.

### 5c. Create the MR

First, detect whether this is a certified project:

<!-- project-config-detection:begin — shared verbatim across @ship and @build -->
```bash
# Detect certified project — three states: CERTIFIED / STANDARD / UNPARSEABLE
# Only literal true/True/TRUE count as certified; false/False/FALSE are standard;
# anything else (quoted strings, yes, on, 1) exits 1 to prevent silent fallback
if [ -f ".agents/project.yaml" ]; then
  if grep -qE '^certified:[[:space:]]*(true|True|TRUE)[[:space:]]*(#.*)?$' .agents/project.yaml; then
    echo "CERTIFIED_PROJECT"
  elif grep -qE '^certified:[[:space:]]*(false|False|FALSE)[[:space:]]*(#.*)?$' .agents/project.yaml; then
    echo "STANDARD_PROJECT"
  elif grep -qE '^certified:[[:space:]]' .agents/project.yaml; then
    LINE=$(grep -E '^certified:' .agents/project.yaml | head -1)
    echo "Error: .agents/project.yaml has certified line but value not recognized:" >&2
    echo "  $LINE" >&2
    echo "Only literal true/True/TRUE or false/False/FALSE accepted (no quotes, no 'yes'/'on')." >&2
    exit 1
  else
    echo "STANDARD_PROJECT"
  fi
else
  echo "STANDARD_PROJECT"
fi
```
<!-- project-config-detection:end -->

Project type: captured from the snippet output. If the snippet exits 1, @ship aborts — no silent fallback to batched MR.

#### Certified Projects: Per-Slice MRs

For certified projects (e.g. HITRUST E1), create one MR per slice in dependency order:

```bash
if [ "$PROJECT_TYPE" = "CERTIFIED_PROJECT" ]; then
  IMPL_FILE=".agents/artifacts/${LABEL}-impl-progress.md"
  BOARD_FILE=".agents/artifacts/${LABEL}-kanban-board.md"
  
  if [ ! -f "$IMPL_FILE" ]; then
    echo "Error: impl-progress artifact not found at $IMPL_FILE"
    echo "Cannot determine slice boundaries for per-slice MRs"
    exit 1
  fi
  
  if [ ! -f "$BOARD_FILE" ]; then
    echo "Error: kanban board not found at $BOARD_FILE"
    echo "Cannot determine slice dependencies for per-slice MRs"
    exit 1
  fi
  
  # Guard yq availability
  if ! command -v yq >/dev/null 2>&1; then
    echo "Error: yq not found — required for certified project MR creation"
    exit 1
  fi
  
  # Derive epic branch deterministically (handles resume after /clear)
  EPIC_BRANCH=$(echo "$BRANCH" | sed -E 's/-s[0-9]+$//')
  
  # Get slice count from frontmatter
  SLICE_COUNT=$(yq --front-matter=process eval '.slices | length' "$BOARD_FILE" | head -1)
  case "$SLICE_COUNT" in
    ''|*[!0-9]*) echo "Error: could not parse slice count from board"; exit 1 ;;
    0) echo "Error: board has no slices"; exit 1 ;;
  esac
  echo "Creating $SLICE_COUNT per-slice MRs"
  
  # Iterate through slices in order (1, 2, 3, ...)
  for i in $(seq 1 $SLICE_COUNT); do
    # Extract slice metadata from board (dependency info)
    SLICE_ID=$(yq --front-matter=process eval ".slices[$((i-1))].id" "$BOARD_FILE" | head -1)
    SLICE_TITLE=$(yq --front-matter=process eval ".slices[$((i-1))].title" "$BOARD_FILE" | head -1)
    SLICE_DESC=$(yq --front-matter=process eval ".slices[$((i-1))].description // \"\"" "$BOARD_FILE" | head -1)
    
    # Derive MR base from blocked_by — respects dependency order
    BLOCKED_BY=$(yq --front-matter=process eval \
      ".slices[$((i-1))].blocked_by | join(\",\")" "$BOARD_FILE" | head -1)
    
    case "$BLOCKED_BY" in
      "")   MR_BASE="$EPIC_BRANCH" ;;
      *,*)  echo "Error: multi-dep slice $SLICE_ID not supported in certified mode"
            echo "Slice $SLICE_ID has dependencies: $BLOCKED_BY"
            echo "Certified projects require linear dependency chains"
            exit 1 ;;
      *)    MR_BASE="${EPIC_BRANCH}-s${BLOCKED_BY}"
            if ! git show-ref --verify --quiet "refs/heads/$MR_BASE"; then
              echo "Error: parent branch $MR_BASE doesn't exist for slice $SLICE_ID"
              exit 1
            fi ;;
    esac
    
    # Determine slice branch name
    SLICE_BRANCH="${EPIC_BRANCH}-s${SLICE_ID}"
    if ! git show-ref --verify --quiet "refs/heads/$SLICE_BRANCH"; then
      echo "Error: slice branch $SLICE_BRANCH doesn't exist"
      exit 1
    fi
    
    echo "Creating MR for Slice $SLICE_ID: $SLICE_TITLE"
    echo "  Branch: $SLICE_BRANCH → $MR_BASE"
    
    # Push the slice branch
    git push -u origin "$SLICE_BRANCH" || {
      echo "Error: failed to push $SLICE_BRANCH"
      exit 1
    }
    
    # Create MR with slice-specific title
    MR_TITLE="${LABEL}-s${SLICE_ID}: ${SLICE_TITLE}"
    
    # GitHub
    if [ "$FORGE" = "github" ]; then
      gh pr create \
        --title "$MR_TITLE" \
        --body "$(cat <<EOF
## Slice ${SLICE_ID}: ${SLICE_TITLE}

${SLICE_DESC}

Part of ${LABEL} implementation.

🤖 AI-assisted
EOF
)" \
        --head "$SLICE_BRANCH" \
        --base "$MR_BASE" \
        --assignee @me || {
          echo "Error: failed to create MR for slice $SLICE_ID"
          exit 1
        }
    # GitLab
    elif [ "$FORGE" = "gitlab" ]; then
      glab mr create \
        --title "$MR_TITLE" \
        --description "$(cat <<EOF
## Slice ${SLICE_ID}: ${SLICE_TITLE}

${SLICE_DESC}

Part of ${LABEL} implementation.

🤖 AI-assisted
EOF
)" \
        --source-branch "$SLICE_BRANCH" \
        --target-branch "$MR_BASE" \
        --assignee @me || {
          echo "Error: failed to create MR for slice $SLICE_ID"
          exit 1
        }
    else
      echo "Error: unknown forge — cannot create per-slice MRs automatically"
      echo "Create MRs manually: $SLICE_BRANCH → $MR_BASE"
      exit 1
    fi
  done
  
  echo "All per-slice MRs created"
fi
```

#### Standard Projects: Single MR

For non-certified projects, create a single MR as before:

```bash
if [ "$PROJECT_TYPE" = "STANDARD_PROJECT" ]; then
  # Build the description from templates/mr-description.md, filling each section
  # from the plan, the diff, and the review artifact. Include the **Breaking changes**
  # section only when the change actually breaks something — omit it otherwise.

  # GitHub (gh — note --body/--base):
  if [ "$FORGE" = "github" ]; then
    gh pr create \
      --title "<TICKET>: <narrative summary>" \
      --body "$(cat <<'EOF'
## What
<bullet points describing what changed>

## Why
<the reasoning, context, or problem being solved>

## How
<implementation approach — key decisions, patterns, files touched>

## Test plan
<how this was verified>

## Breaking changes
<only if applicable; omit this section otherwise>

🤖 AI-assisted
EOF
)" \
      --base "$TARGET_BRANCH" \
      --assignee @me
  # GitLab (glab — note --description/--target-branch):
  elif [ "$FORGE" = "gitlab" ]; then
    glab mr create \
      --title "<TICKET>: <narrative summary>" \
      --description "$(cat <<'EOF'
## What
<bullet points describing what changed>

## Why
<the reasoning, context, or problem being solved>

## How
<implementation approach — key decisions, patterns, files touched>

## Test plan
<how this was verified>

## Breaking changes
<only if applicable; omit this section otherwise>

🤖 AI-assisted
EOF
)" \
      --target-branch "$TARGET_BRANCH" \
      --assignee @me
  fi
  
  Show the MR URL when done.
fi
```

**If the forge is unknown or its CLI is missing:** do not fail the ship. Report
the branch and detected target branch, then tell the user to open the MR manually
against `$TARGET_BRANCH`.

---

## Step 6: Close Artifacts (last)

Only after the push and MR succeed, mark the artifacts closed so an aborted ship
never leaves them falsely closed. Reuse the `${LABEL}` resolved in Step 2.

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

```bash
CLOSED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

for f in ".agents/artifacts/${LABEL}-plan.md" ".agents/artifacts/${LABEL}-kanban-board.md"; do
  if [ -f "$f" ]; then
    sed -i "s/^status: .*/status: closed/" "$f"
    # Add closed timestamp after the status line if not present
    grep -q '^closed:' "$f" || sed -i "/^status: /a closed: $CLOSED" "$f"
    echo "Closed: $f"
  fi
done

[ -f ".agents/artifacts/${LABEL}-impl-progress.md" ] && sed -i "s/^status: .*/status: closed/" ".agents/artifacts/${LABEL}-impl-progress.md"
```

---

## Quality Bar

- Never ship if the working tree is dirty — `@ship` does not commit
- Never ship if the verification suite (Step 1) fails
- Always check review freshness against `reviewed_head` before shipping
- Never autosquash once the commits have been pushed
- Always detect the MR target branch from the branch's creation point — never hardcode it
- Always detect the forge (GitHub vs GitLab) from the origin remote — never assume one
- Never force-push unless the user explicitly asks
- If the branch has no upstream yet, `-u origin <BRANCH>` sets it automatically
- Close the plan, kanban and progress artifacts only after the push and MR succeed
