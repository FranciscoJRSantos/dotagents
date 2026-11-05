---
name: plan
description: >
  Generates a type-aware implementation plan with Kanban/DAG vertical slices and
  presents it for approval before writing artifacts. Sources the plan from a Jira
  ticket (@plan PROJ-123) or from a local @grill-me decision log (@plan grill-<slug>,
  or @plan with no argument to pick from a list). Produces both a plan artifact and
  a kanban-board artifact.
  Entry point: @plan PROJ-123 | @plan grill-<slug>
---

# Plan Skill

Produces a structured, type-aware implementation plan with a Kanban board of
vertical slices, sourced either from a Jira ticket or from a local `@grill-me`
decision log. Nothing is written to Jira until the user explicitly approves.

---

## Gotchas

- `acli jira get` often returns sparse output for tickets with custom fields — fall back to `acli jira workitem view --json` immediately if key fields (description, type) are missing.
- Ticket type detection can fail for hybrid tickets (e.g. a Feature with ML evaluation components). When in doubt, ask the user rather than guessing — getting the type wrong produces a structurally mismatched plan.
- Never invent metric values, thresholds, or acceptance criteria — if the ticket doesn't specify them, mark them as `TBD` and flag this to the user before proceeding.
- `acli jira workitem comment create` accepts `--body-file` for ADF JSON. Always convert markdown plans to ADF before posting (Step 5 handles this).

---

## Step 1: Determine the Source

`@plan` takes one of three inputs:

| Invocation | Source | Jira access |
|---|---|---|
| `@plan PROJ-123` | the Jira ticket | fetch + post |
| `@plan grill-<slug>` | `.agents/artifacts/grill-<slug>-decisions.md` | none |
| `@plan` | pick from the grill logs on disk | none |

### 1a. Jira key

Load only the grill logs that name this ticket — never glob for unrelated logs:

```bash
KEY=PROJ-123
for f in .agents/artifacts/grill-*-decisions.md; do
  [ -f "$f" ] || continue
  grep -q "^ticket: ${KEY}$" "$f" && echo "$f"
done
```

Read any matches to incorporate resolved decisions into the plan.

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

### 1b. Grill log

```bash
SLUG=<slug>
LOG=".agents/artifacts/grill-${SLUG}-decisions.md"
[ -f "$LOG" ] || { echo "No grill log at $LOG"; exit 1; }
cat "$LOG"
```

Build the plan from the log's Resolved Decisions. Do not fetch or post to Jira.
When this plan is written, mark the log consumed (Step 8b).

### 1c. No argument

List the available logs and ask the user to pick one:

```bash
ls .agents/artifacts/grill-*-decisions.md 2>/dev/null
```

If there are none, ask for a Jira key and continue with 1a.

---

## Step 2: Detect Ticket Type

Determine the type from the ticket content. In grill mode there is no Jira issue
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
- Every slice defaults to `mode: hitl` — it stops at the gate for human review
- `mode: afk` is only for work that can run unattended: pure refactors, boilerplate,
  or changes fully covered by tests with cheap failure modes. Justify every `afk`
  slice in its `description`; when in doubt, use `hitl`
- Slices with no blocking dependencies can run concurrently — that is derivable
  from `blocked_by: []`, so it needs no separate tag
- Slices that block others should have their `blocks` field set

Example vertical slice decomposition:

```yaml
slices:
  - id: 1
    title: "Define types and schemas"
    description: "Core data types that all downstream modules depend on"
    mode: hitl
    blocks: [2, 3]
    blocked_by: []
    module_interfaces:
      - module: "src/models.py"
        public_interface: "Item(BaseModel), ItemCreate(Item), ItemUpdate(Item)"
        test_boundaries: "Construction, validation, serialization"
  - id: 2
    title: "Implement business logic"
    description: "Pure domain logic for item processing"
    mode: hitl
    blocks: [5]
    blocked_by: [1]
    module_interfaces:
      - module: "src/service.py"
        public_interface: "process_item(item: Item) -> Result, validate_schema(data: dict) -> Item"
        test_boundaries: "Happy path, edge cases, error states"
  - id: 3
    title: "Add API endpoints"
    description: "REST endpoints for CRUD operations"
    mode: hitl
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

- **Jira key:** *"Does this plan look right? Say 'approved' to post it as a Jira comment and write artifacts, or tell me what to adjust."*
- **Grill log:** *"Does this plan look right? Say 'approved' to write the plan and kanban artifacts, or tell me what to adjust."*

Do not write anything yet.

---

## Step 8: Write Artifacts

The user must say "approved", "yes", "lgtm", or similar. If they ask for changes,
revise the plan and show the updated version.

### 8a. Write to Jira (Jira key mode only)

Skip this step entirely in grill mode — there is no Jira ticket to comment on.

First check available flags:

```bash
acli jira workitem comment --help
```

Then convert the markdown plan to Atlassian Document Format (ADF) and post it.
The converter sits beside this `SKILL.md`. Claude Code substitutes
`${CLAUDE_SKILL_DIR}` in the skill content, while OpenCode exposes no such
substitution, so fall back to its deployed path:

```bash
# Resolve this skill's directory
SKILL_DIR="${CLAUDE_SKILL_DIR}"
[ -n "$SKILL_DIR" ] || SKILL_DIR="$HOME/.config/opencode/skills/plan"

# Save the plan markdown to a temp file
PLAN_MD=$(mktemp)
cat > "$PLAN_MD" <<'EOF'
[paste the full approved plan markdown here]
EOF

# Convert to ADF JSON, guarding against a converter hang
PLAN_JSON=$(mktemp)
if timeout 10 python3 "$SKILL_DIR/md_to_adf.py" "$PLAN_MD" "$PLAN_JSON"; then
  acli jira workitem comment create --key PROJ-123 --body-file "$PLAN_JSON"
else
  echo "ADF conversion failed or timed out — posting the plan as plain text instead."
  acli jira workitem comment create --key PROJ-123 --body-file "$PLAN_MD"
fi

# Clean up
rm "$PLAN_MD" "$PLAN_JSON"
```

Confirm the comment was posted and show the ticket URL or key.

### 8b. Write Plan Artifact

Resolve the artifact label from the current branch name — the ticket key when the
branch carries one, otherwise the branch name with `/` replaced by `-`:

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

Write `.agents/artifacts/<LABEL>-plan.md`. `ticket` is the Jira key argument in
Jira mode and `null` in grill mode; `status` is `posted` in Jira mode and `active`
in grill mode:

```yaml
---
artifact: plan
ticket: <Jira key or null>
skill: plan
created: <ISO 8601 timestamp>
status: posted        # or: active in grill mode
---
```

Followed by the full plan content.

In grill mode, mark the source log as consumed so the same decisions are not
planned twice:

```bash
LOG=".agents/artifacts/grill-<slug>-decisions.md"
grep -q '^consumed_by:' "$LOG" || sed -i "/^skill: grill-me/a consumed_by: ${LABEL}-plan.md" "$LOG"
```

### 8c. Write Kanban Board Artifact

Write `.agents/artifacts/<LABEL>-kanban-board.md`:

```yaml
---
artifact: kanban-board
ticket: <Jira key or null>
skill: plan
created: <ISO 8601 timestamp>
status: active
slices:
  - id: 1
    title: <slice title>
    description: <what this slice delivers>
    mode: hitl          # or: afk — justify every afk in the description
    blocks: [<slice IDs>]
    blocked_by: [<slice IDs>]
    module_interfaces:
      - module: <path>
        public_interface: <methods/types>
        test_boundaries: <boundary description>
  - id: 2
    ...
---
```

This artifact is read by `@implement` to know which slice to work on and to resume.

Run `/clear` before `@implement` to start implementation in a fresh context window.

---

## Quality Bar

A good plan should:
- Use exact values from the ticket (metrics, thresholds, criteria) — never invent them
- Be executable: someone unfamiliar with the ticket can follow the steps
- Be proportionate: a small QoL change doesn't need 5 pages; an ML experiment does
- Surface risks or ambiguities the ticket author may not have considered
- Leave the "out of scope" section explicit, not implied
- Decompose into vertical slices where each slice delivers something testable
- Set each slice's mode (default `hitl`; justify every `afk`) for correct routing during implementation
