---
name: arch
description: >
  Generates a type-aware implementation plan with Kanban/DAG vertical slices and
  presents it for approval before writing artifacts. Sources the plan from a Jira
  ticket (@arch PROJ-123) or from a local @spec decision log (@arch <slug>,
  or @arch with no argument to pick from a list). Produces both a plan artifact and
  a kanban-board artifact.
  Entry point: @arch PROJ-123 | @arch <slug>
---

# Arch Skill

Produces a structured, type-aware implementation plan with a Kanban board of
vertical slices, sourced either from a Jira ticket or from a local `@spec`
decision log. Nothing is written to Jira until the user explicitly approves.

**All slices default to `mode: afk`** — autonomous execution with no per-slice
human gates. The agent runs end-to-end, only stopping when risk classification
requires human review (at `@review`).

---

## Conversation Density

**Conversation is routing only.** Keep conversation output to 1-3 lines per decision.
Write all detail to artifacts. The user reads conversation for decisions, drills into
artifacts for detail.

- Plan text → artifact
- Kanban board → artifact
- Conversation: "Plan written to `<path>`. N slices, M dependencies. Review or say 'approved'."

---

## Gotchas

- `acli jira get` often returns sparse output for tickets with custom fields — fall back to `acli jira workitem view --json` immediately if key fields (description, type) are missing.
- Ticket type detection can fail for hybrid tickets (e.g. a Feature with ML evaluation components). When in doubt, ask the user rather than guessing — getting the type wrong produces a structurally mismatched plan.
- Never invent metric values, thresholds, or acceptance criteria — if the ticket doesn't specify them, mark them as `TBD` and flag this to the user before proceeding.
- `acli jira workitem comment create` accepts `--body-file` for ADF JSON. Always convert markdown plans to ADF before posting (Step 5 handles this).

---

## Step 1: Determine the Source

`@arch` takes one of three inputs:

| Invocation | Source | Folder | Jira access |
|---|---|---|---|
| `@arch <slug>` | `<slug>/decisions.org` | `<slug>` | none |
| `@arch PROJ-123` | the Jira ticket, plus any log with `#+TICKET: PROJ-123` | that log's folder, else `proj-123-<summary>` | fetch + post |
| `@arch` | pick from folders with `decisions.org` and no `plan.org` | the picked one | none |

`~/.agents/bin/artifact-dir <slug>` resolves a folder: it prints
`ARTIFACT_DIR=<path>`, moves an archived folder back (`REOPENED: <slug>`), and
exits 1 with `NOT FOUND: <slug>` on a typo. Do not run it under `set -e`.

### 1a. Slug

```bash
OUT=$(~/.agents/bin/artifact-dir "<slug>"); rc=$?
echo "$OUT"
DIR=$(printf '%s\n' "$OUT" | sed -n 's/^ARTIFACT_DIR=//p')
```

On `rc != 0`, show the output and ask for the right slug. Otherwise read the log:

```bash
cat "$DIR/decisions.org"
```

Build the plan from its Resolved Decisions and take `TICKET` from its keyword
(empty when absent). Do not fetch or post to Jira.

```bash
TICKET=$(grep -m1 '^#+TICKET:' "$DIR/decisions.org" | cut -d' ' -f2)
```

### 1b. Jira key

Find the work folders that name this ticket — by keyword in any of their `.org`
files, never by folder name, the same scope `artifact-dir` uses — active work first,
then archived:

```bash
KEY=PROJ-123
TICKET=$KEY
for root in .agents/artifacts .agents/archive; do
  M=$(grep -lx "#+TICKET: $KEY" "$root"/*/*.org 2>/dev/null |
      xargs -r -n1 dirname | xargs -r -n1 basename | sort -u)
  [ -n "$M" ] && { echo "$M"; break; }
done
```

- **One folder** — pass it to `artifact-dir` as in 1a (this reopens an archived
  one) and read its `decisions.org`, if any, to incorporate the resolved decisions.
  If it already has a `plan.org`, ask before replacing it.
- **Several folders** — list them and ask which one this plan belongs to.
- **None** — name the folder after the ticket once its summary is known (below),
  and never write into a folder that already exists under that name:

  ```bash
  SLUG=$(~/.agents/bin/slug "$KEY <summary>")
  DIR=".agents/artifacts/$SLUG"
  for d in "$DIR" ".agents/archive/$SLUG"; do
    [ -e "$d" ] && echo "EXISTS: $d"
  done
  ```

  On `EXISTS`, show the path and ask the user for the folder name to use.

Fetch the ticket from Jira:

```bash
acli jira get PROJ-123
```

If output is sparse, try:

```bash
acli jira workitem view PROJ-123 --json
```

Extract:
- Summary / title
- Description (full text, including any structured fields)
- Issue type
- Acceptance criteria (explicit or implied)
- Any linked tickets or context

### 1c. No argument

List the folders with a `decisions.org` and no `plan.org` yet — those are the
unplanned specs:

```bash
for d in .agents/artifacts/*/; do
  [ -f "$d/decisions.org" ] && [ ! -f "$d/plan.org" ] && basename "$d"
done
```

If there are none, ask for a Jira key and continue with 1b.

---

## Step 2: Detect Ticket Type

Determine the type from the ticket content. In decision log mode there is no Jira issue
type — infer the plan structure from the decision log's scope, or ask the user
which structure (ML experiment, API QoL, CI/CD, Feature, Epic) fits best.

| Type | Signals |
|------|---------|
| **ML experiment** | hypothesis, model, training, metric, baseline, eval |
| **API QoL** | endpoint, response, latency, client, schema, backwards compat |
| **CI/CD** | pipeline, deploy, workflow, GitHub Actions, build, infra |
| **Feature** | user story, product behaviour, acceptance criteria |
| **Epic** | issuetype = Epic, large body of work, multiple child issues, quarter-long scope |

If the ticket is an Epic (Jira mode only), fetch child issues before proceeding to Step 3:

```bash
acli jira workitem search --jql 'parent = PROJ-123' --json
```

Group child issues by status (Done/Cancelled vs. open) and by theme (e.g. model training,
infra, API, experiments). This becomes the input for the Epic Breakdown Plan.

If genuinely ambiguous, ask the user to clarify before proceeding.

---

## Step 3: Generate the Plan

Produce a detailed plan using the structure for the detected type. Pull specific
values (metrics, thresholds, criteria) directly from the ticket — never invent them.

---

### ML Experiment Plan

```markdown
## Hypothesis
[Exact hypothesis from ticket — falsifiable, with expected direction and magnitude]

## Experiment Design
- **What changes:** [model components, training config, data pipeline]
- **What is controlled:** [everything held constant to isolate the variable]
- **Run configuration:** [framework, hardware, seed, reproducibility notes]

## Implementation Steps
1. Data preparation — [any preprocessing, splits, or augmentation needed]
2. Model changes — [architecture or config changes]
3. Training — [run command, wandb project/group, expected duration]
4. Evaluation — [eval script, dataset, how metrics are computed]

## Evaluation Criteria
| Metric | Baseline | Success Threshold | Source |
|--------|----------|-------------------|--------|
| [metric] | [value from ticket] | [threshold from ticket] | [ticket field] |

## Failure Criteria and Next Steps
- **Failure if:** [condition that clearly indicates the hypothesis is false]
- **Next steps on failure:** [from ticket, or derived — next hypothesis, ablation, stop]
```

---

### API QoL Plan

```markdown
## Current Behaviour
[Summary of what the API does today — status codes, payloads, latency if known]

## Proposed Change
[Interface definition: endpoint, method, request/response schema]

## Backwards Compatibility Analysis
- Breaking change: [yes/no and why]
- Migration required: [which consumers, what they need to change]
- Deprecation timeline: [if applicable]

## Affected Consumers
| Consumer | Impact | Migration needed |
|----------|--------|-----------------|
| [service/team] | [what breaks or changes] | [yes/no + notes] |

## Implementation Steps
1. [ordered steps]

## Test Plan
- Schema contract tests: [what to validate]
- Status code tests: [expected codes per scenario]
- Latency regression: [threshold and measurement method]
```

---

### CI/CD Plan

```markdown
## Current State
[What the pipeline/workflow does today]

## Target State
[What it will do after — be specific]

### Definition of Done
[Exact, production-observable criteria — not "pipeline passes" but e.g.
"deploy job completes in <3 min on merge to main; canary error rate stays
below 0.1% for 10 minutes post-deploy; alert X stays silent"]

## Implementation Steps
| Step | Description | Rollback point |
|------|-------------|---------------|
| 1 | [action] | [how to revert this step alone] |
| 2 | [action] | [how to revert this step alone] |

## Verification Steps
How to confirm this is working in production:
1. [observable check — specific metric, log, dashboard, or alert]
2. [...]

## Rollback Procedure
[Ordered steps to fully revert if the change causes a production incident]
```

---

### Feature Plan

```markdown
## User Story
[As a [role] I want [capability] so that [outcome]]

## Acceptance Criteria
- [ ] [testable condition]
- [ ] [testable condition]

## Technical Approach
[Architecture decisions, key components, data flow]

## Implementation Steps
1. [ordered steps]

## Out of Scope
- [explicit list — related things this ticket does NOT cover]

## Test Plan
- Unit: [what to test at the unit level]
- Integration: [what to test end-to-end]
- Manual verification: [what to check by hand before merging]
```

---

### Epic Breakdown Plan

```markdown
## Problem Statement
[Why this epic exists — the chronic issue or gap it addresses, and why it has no end today]

## Proposed Bounded Sub-Epics

| Sub-Epic | End Condition | Open Work | Done Work |
|----------|---------------|-----------|-----------|
| [name] | [observable, specific — not "improve X"] | [ticket keys] | [ticket keys] |

## Recurring Work → Process
[List any child issues that repeat on a cycle. These should become a documented
process/runbook rather than tickets in a perpetual epic. Each cycle gets its own
short-lived versioned epic, not a backlog item in a catch-all.]

## Child Issues Reassignment
| Ticket | Summary | Proposed Destination |
|--------|---------|---------------------|
| [key] | [title] | [sub-epic name or PROCESS] |

## Definition of Done for Each Sub-Epic
[For each proposed sub-epic, state the exact observable condition that closes it.
Never accept "ongoing" or "as needed" — every epic must have an end state.]
```

---

## Step 4: Module Interface Design

This step maps the plan's implementation steps to specific modules, their public
interfaces, and test boundaries. The output feeds directly into the Kanban slice
definitions in Step 5.

For each new or modified module in the plan, define:

| Module | Public Interface | Test Boundaries | Layer |
|--------|-----------------|-----------------|-------|
| `<file path>` | `<methods/types/functions exported>` | `<what to test at the module boundary>` | `<data/pure/edge/ui/integration>` |

Derive the module list from the implementation steps. For each step:
1. Identify which file(s) need to be created or modified
2. List the public API each module will expose
3. Define what constitutes a valid test boundary (inputs → outputs, side effects, error cases)
4. Tag the layer: `data` (schemas, types), `pure` (business logic), `edge` (I/O), `ui` (presentation), `integration` (wiring)

This module map is embedded in the Kanban board artifact as `module_interfaces` per slice.

---

## Step 5: Verify Plan Completeness

Before showing the plan to the user, run an automated verification against it:

1. **AC-to-Step traceability:** Does every acceptance criterion from the ticket have at least one implementation step that addresses it?
2. **Step-to-Verification traceability:** Does every implementation step have a corresponding test/verification section?
3. **Circular dependencies:** Are any steps in the plan mutually dependent on each other?
4. **TBD metrics (ML and CI/CD plans only):** Scan for "TBD", "to be determined", "to be defined" in metrics, thresholds, and criteria — this duplicates the Step 7 gate but is an earlier catch.

Run these checks against the generated plan text. If any issues are found, fix them in the plan before proceeding. If all checks pass, proceed.

If the plan is an Epic Breakdown, also verify: every sub-epic has an end condition, and no sub-epic is defined as "ongoing" or "as needed."

---

## Step 6: Decompose into Kanban Slices

After the plan is verified and the module interfaces are designed, decompose the work
into vertical slices. Each slice crosses all layers (data → pure → edge → UI → integration)
and delivers something testable.

Group the module interfaces from Step 4 into slices by dependency order:

1. Identify modules with no dependencies — these form the first slice(s)
2. Group remaining modules by their dependency chain
3. Assign each slice an ID, title, description, and mode

**Slice rules:**
- Each acceptance criterion → at least one slice that addresses it
- **Every slice defaults to `mode: afk`** — autonomous execution, no per-slice human gates
- `mode: hitl` is only for work that explicitly requires human review before proceeding. Justify every `hitl` slice in its `description`; when in doubt, use `afk`
- Slices with no blocking dependencies can run concurrently — that is derivable
  from `blocked_by: []`, so it needs no separate tag
- Slices that block others should have their `blocks` field set

Example vertical slice decomposition:

```yaml
slices:
  - id: 1
    title: "Define types and schemas"
    description: "Core data types that all downstream modules depend on"
    mode: afk
    blocks: [2, 3]
    blocked_by: []
    module_interfaces:
      - module: "src/models.py"
        public_interface: "Item(BaseModel), ItemCreate(Item), ItemUpdate(Item)"
        test_boundaries: "Construction, validation, serialization"
  - id: 2
    title: "Implement business logic"
    description: "Pure domain logic for item processing"
    mode: afk
    blocks: [5]
    blocked_by: [1]
    module_interfaces:
      - module: "src/service.py"
        public_interface: "process_item(item: Item) -> Result, validate_schema(data: dict) -> Item"
        test_boundaries: "Happy path, edge cases, error states"
  - id: 3
    title: "Add API endpoints"
    description: "REST endpoints for CRUD operations"
    mode: afk
    blocks: [5]
    blocked_by: [1]
    module_interfaces:
      - module: "src/api.py"
        public_interface: "POST /items, GET /items/{id}, DELETE /items/{id}"
        test_boundaries: "Status codes, payload validation, auth errors"
```

---

## Step 7: Present for Approval

Show the full plan and the Kanban board decomposition.

**For ML experiment and CI/CD plans only, scan success metrics and thresholds for
placeholder values before asking for approval.** Check the Evaluation Criteria
table (ML plans) and Definition of Done (CI/CD plans) for:
- The literal string "TBD" or "to be determined" or "to be defined"
- Blank / empty threshold cells
- Qualitative-only descriptions with no numeric bound (e.g. "improves performance", "reduces latency", "better than baseline")

If any are found, do NOT show the approval prompt. Instead show:

```
BLOCKED: The following metrics have no numeric threshold and cannot be used to
evaluate experiment success or failure:

- [metric name]: "[current placeholder value]"

Please provide a specific numeric threshold for each before this plan can be approved
(e.g. "AUC-ROC ≥ 0.85" rather than "improves AUC-ROC").
```

Only show the approval prompt once all thresholds are concrete and numeric (or
explicitly N/A with a stated reason). Feature, API QoL and Epic plans skip this
gate — their acceptance criteria are testable conditions, not numeric thresholds.
The prompt names what approval does in the current mode:

- **Jira key:** *"Does this plan look right? Say 'approved' to post it as a Jira comment and write `plan.org` and `board.org`, or tell me what to adjust."*
- **Slug:** *"Does this plan look right? Say 'approved' to write `plan.org` and `board.org`, or tell me what to adjust."*

Do not write anything yet.

---

## Step 8: Write Artifacts

The user must say "approved", "yes", "lgtm", or similar. If they ask for changes,
revise the plan and show the updated version.

Save the approved plan Markdown once. The same file feeds the Jira comment (8b)
and `plan.org` (8c), so the two never drift:

```bash
PLAN_MD=$(mktemp --suffix=.md)
cat > "$PLAN_MD" <<'EOF'
[paste the full approved plan markdown here — no # Title line, no frontmatter]
EOF
```

### 8a. Make sure the folder is ignored

`$DIR` is the folder resolved in Step 1. First make sure `.agents/` ignores its own
state:

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

```bash
mkdir -p "$DIR"
```

### 8b. Write to Jira (Jira key mode only)

Skip this step entirely in slug mode — there is no Jira ticket to comment on.

First check available flags:

```bash
acli jira workitem comment --help
```

Then convert the plan to Atlassian Document Format (ADF) and post it. The converter
sits beside this `SKILL.md`. Claude Code substitutes `${CLAUDE_SKILL_DIR}` in the
skill content, while OpenCode exposes no such substitution, so fall back to its
deployed path:

```bash
# Resolve this skill's directory
SKILL_DIR="${CLAUDE_SKILL_DIR}"
[ -n "$SKILL_DIR" ] || SKILL_DIR="$HOME/.config/opencode/skills/arch"

# Convert to ADF JSON, guarding against a converter hang
PLAN_JSON=$(mktemp)
if timeout 10 python3 "$SKILL_DIR/md_to_adf.py" "$PLAN_MD" "$PLAN_JSON"; then
  acli jira workitem comment create --key PROJ-123 --body-file "$PLAN_JSON"
else
  echo "ADF conversion failed or timed out — posting the plan as plain text instead."
  acli jira workitem comment create --key PROJ-123 --body-file "$PLAN_MD"
fi
rm -f "$PLAN_JSON"
```

Confirm the comment was posted and show the ticket URL or key.

### 8c. Write `plan.org`

Convert the same Markdown. `TICKET` comes from Step 1 (empty in slug mode without
a ticket, and then omitted); add `JIRA_COMMENT="<url>"` when 8b returned one:

```bash
~/.agents/bin/md2org "$PLAN_MD" "$DIR/plan.org" TITLE="Plan: <title>" TICKET="$TICKET" &&
  rm -f "$PLAN_MD"
```

`md2org` must exit 0 before you continue. On a non-zero exit it prints `file:line`
per Markdown leftover and keeps both files: fix the lines in `$PLAN_MD` and run it
again.

### 8d. Write `board.org`

`board.org` is the one artifact written as Org directly, from this template. It
holds every slice's definition and, through its TODO keywords, its state —
`@build` advances it with `sed`, so keep the shapes exact:

- One `* TODO Slice <N>: <title>` heading per slice, all starting as `TODO`.
- The property drawer comes right after the heading. `:SLICE:` (never `:ID:`,
  which org-id owns), `:MODE:` `hitl` or `afk`, `:BLOCKS:` and `:BLOCKED_BY:` as
  space-separated slice numbers (empty when none), and `:COMMIT:` always present
  and empty.
- Then the description (justify every `afk` there) and a `** Module interfaces`
  list. Write Org markup: `=path=` and `~code~`, `*bold*`, never backticks or `**`.

```org
#+TITLE: Board: <title>
#+CREATED: <ISO 8601 timestamp, UTC>
#+TODO: TODO DOING | DONE SKIPPED

* TODO Slice 1: <slice title>
:PROPERTIES:
:SLICE: 1
:MODE: hitl
:BLOCKS: 2 3
:BLOCKED_BY:
:COMMIT:
:END:
<what this slice delivers; for afk, why it is safe to run unattended>

** Module interfaces
- =<path>= — <public interface>. Tests: <test boundaries>

* TODO Slice 2: <slice title>
:PROPERTIES:
:SLICE: 2
:MODE: hitl
:BLOCKS:
:BLOCKED_BY: 1
:COMMIT:
:END:
<description>

** Module interfaces
- =<path>= — <public interface>. Tests: <test boundaries>
```

Then check it, and fix any reported line before finishing:

```bash
~/.agents/bin/org-check "$DIR/board.org"
```

`@build` reads `plan.org` and `board.org` from this folder to pick and resume
slices. Run `/clear` before `@build` to start implementation in a fresh context
window.

---

## Quality Bar

A good plan should:
- Use exact values from the ticket (metrics, thresholds, criteria) — never invent them
- Be executable: someone unfamiliar with the ticket can follow the steps
- Be proportionate: a small QoL change doesn't need 5 pages; an ML experiment does
- Surface risks or ambiguities the ticket author may have considered
- Leave the "out of scope" section explicit, not implied
- Decompose into vertical slices where each slice delivers something testable
- **Default every slice to `mode: afk`** for autonomous execution; justify every `hitl` slice
