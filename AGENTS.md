# Agents Guide: dotagents

Skills run in the main conversation and write artifacts, invoked with
`@<skill-id>`; agents are isolated subagents that return findings only.

```
skills/<name>/SKILL.md   ← one skill per file
agents/<name>.md         ← one agent per file
```

`make deploy` syncs skills, agents and commands to OpenCode and Claude Code,
generating the Claude Code agent variants and installing the shared `partials/` to
`~/.agents/`.
Personal global rules live at `global/AGENTS.md` (gitignored; template
`global/AGENTS.md.example`). See the [README](README.md) for the targets and the
`make lint` / `make drift` commands.

## Skills vs Agents

|                      | Skills                   | Agents                                               |
|----------------------|--------------------------|------------------------------------------------------|
| **Invocation**       | `@<skill-id>`            | `@agent-name` or auto-matched by description         |
| **Writes artifacts** | Yes                      | No — findings only                                   |
| **Best for**         | Workflows, orchestration | File-heavy reading that shouldn't bloat main context |

## Artifact Chain

Skills hand context to each other through `.agents/artifacts/<slug>/`:

| Artifact                    | Written by  | Read by              |
|-----------------------------|-------------|----------------------|
| `<slug>/decisions.org`      | `@spec`     | `@arch`              |
| `<slug>/plan.org`           | `@arch`     | `@review`, `@ship`   |
| `<slug>/board.org`          | `@arch`     | `@build`             |
| `<slug>/review.org`         | `@review`   | `@ship`              |

`<slug>` is the work folder name, resolved by `artifact-dir` (explicit slug, ticket
key via `#+TICKET:`, or the only active folder). Schemas live with their owners:
the board shape in `skills/arch/SKILL.md`, the decision log in `skills/spec/SKILL.md`,
the review report in `~/.agents/partials/review-rules.md`, risk classification in
`~/.agents/partials/risk-classifier.md`.

## Workflow

```
@spec → @arch → @build → @review → @ship
```

This is the **software factory model**: humans own specs/plans (upstream), agents
own implementation/review (downstream). `@build` runs all slices autonomously —
no per-slice human gates. `@review` is the HITL point, where risk classification
determines whether human review is needed. Conversation output is terse (1-3 lines
of routing); detail lives in artifacts.

`@build` runs each vertical slice through Explore → RED → GREEN → REFACTOR →
checks → inner `reviewer` → commit; see `skills/build/SKILL.md`. Run
`@codemap` first on an unfamiliar codebase — `@observer` keeps the map current.

## Certified Projects

For compliance requirements (e.g. HITRUST E1), projects can opt into per-slice
merge requests. Create `.agents/project.yaml` with `certified: true`:

```yaml
certified: true
```

When certified:
- `@build` creates a separate branch for each slice (`${BRANCH}-s${N}`)
- `@ship` creates one MR per slice in dependency order, targeting the parent branch
- Each slice can be reviewed and merged independently

When not certified (default):
- `@build` commits all slices to a single branch
- `@ship` creates one MR at the end

The detection uses a shared snippet (`<!-- project-config-detection:begin -->`)
embedded in `@build` and `@ship` (three copies total — two in `@ship`, one in
`@build`; kept byte-identical and enforced by
`test_all_three_snippets_are_byte_identical` in
`tests/test_project_config_detection.py`). Only literal `true`/`True`/`TRUE`
values are recognized; quoted strings and YAML 1.1 variants (`yes`, `on`) are not.

## Project State

`.agents/STATE.org` carries cross-session context (branch, position, decisions,
blockers). Work-scoped handoffs live in `<slug>/handoffs/`; standalone handoffs
(when no work folder is active) go to `.agents/handoffs/`. `.agents/` is
disposable and self-ignoring; only `.agents/conventions.md` is tracked, where
captured corrections land for `@learn review`.

## Review Rules Override

The `reviewer` loads `~/.agents/partials/review-rules.md` and overlays
`.agents/review.md` when present. Template: `templates/review.md.example`.

Every skill and agent is listed in the [README](README.md).
