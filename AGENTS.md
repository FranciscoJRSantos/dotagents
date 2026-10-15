# Agents Guide: dotagents

Skills are slash commands that run in the main conversation and write artifacts;
agents are isolated subagents that return findings only.

```
skills/<name>/SKILL.md   ← one skill per file
agents/<name>.md         ← one agent per file
```

`make deploy` syncs skills and agents to OpenCode and Claude Code, generating the
Claude Code agent variants and installing the shared `partials/` to `~/.agents/`.
Personal global rules live at `global/AGENTS.md` (gitignored; template
`global/AGENTS.md.example`). See the [README](README.md) for the targets and the
`make lint` / `make drift` commands.

## Skills vs Agents

|                      | Skills                   | Agents                                               |
|----------------------|--------------------------|------------------------------------------------------|
| **Invocation**       | `/skill-name`            | `@agent-name` or auto-matched by description         |
| **Writes artifacts** | Yes                      | No — findings only                                   |
| **Best for**         | Workflows, orchestration | File-heavy reading that shouldn't bloat main context |

## Artifact Chain

Skills hand context to each other through `.agents/artifacts/`:

| Artifact                    | Written by   | Read by               |
|-----------------------------|--------------|-----------------------|
| `grill-<slug>-decisions.md` | `/grill-me`  | `/plan`               |
| `<LABEL>-plan.md`           | `/plan`      | `/review`, `/ship`    |
| `<LABEL>-kanban-board.md`   | `/plan`      | `/implement`          |
| `<LABEL>-review-impl.md`    | `/review`    | `/ship`               |
| `<LABEL>-impl-progress.md`  | `/implement` | `/implement` (resume) |

`<LABEL>` is the ticket key when the branch carries one, otherwise the branch
name with `/` replaced by `-`. Schemas live with their owners: the kanban/plan
shape in `skills/plan/SKILL.md`, impl-progress in `skills/implement/SKILL.md`,
the grill log in `skills/grill-me/SKILL.md`, the review report in
`~/.agents/partials/review-rules.md`.

## Workflow

```
/grill-me → /plan → /implement → /review → /ship
```

`/implement` runs each vertical slice through Explore → RED → GREEN → REFACTOR →
checks → inner `reviewer` → gate → commit; see `skills/implement/SKILL.md`. Run
`/codemap` first on an unfamiliar codebase — `@observer` keeps the map current.

## Project State

`.agents/STATE.md` carries cross-session context (branch, position, decisions,
blockers). `.agents/` is disposable and self-ignoring; only
`.agents/conventions.md` is tracked, where captured corrections land for
`/learn review`.

## Review Rules Override

The `reviewer` loads `~/.agents/partials/review-rules.md` and overlays
`.agents/review.md` when present. Template: `templates/review.md.example`.

Every skill and agent is listed in the [README](README.md).
