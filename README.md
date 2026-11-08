# dotagents

Research-backed agent skills and subagents for software engineering workflows.
Skills run inside OpenCode or Claude Code and are invoked with `@<skill-id>`;
`/review` is the one overriding slash command.

See [AGENTS.md](AGENTS.md) for the architecture, the artifact chain and the
`.agents/` conventions. That file is the home for the artifact-chain table; this
README covers setup and the catalogue.

## Workflows

**Primary (design → ship):**
```
@spec → @arch → @build → @review → @ship
```

This is the **software factory model**: humans own specs/plans (upstream), agents
own implementation/review (downstream). `@build` runs all slices autonomously —
no per-slice human gates. `@review` is the HITL point, where risk classification
determines whether human review is needed. Conversation output is terse (1-3 lines
of routing); detail lives in artifacts.

**Quick fix (no upfront design):**
```
@build   # ad-hoc: one goal + one acceptance criterion, one reviewed commit
@ship
```

**Ticket already exists in Jira:**
```
@arch TICKET → @build → @review → @ship
```

**Session start on unfamiliar code:**
```
@codemap
```

---

## Setup

```bash
git clone <repo>
make deploy   # sync skills, agents and commands to OpenCode and Claude Code
```

`make deploy` is manifest-based: each target dir keeps a
`.personal-agents-manifest`, and only the items this repo deployed are ever
updated or removed. Anything else at the destination (e.g.
`~/.claude/skills/synced/`, plugin skills, hand-made agents) is left alone.
Preview any deploy with `make deploy DRY_RUN=1`; `make drift` diffs the repo
against every deployed location and never copies.

Skills are invoked with `@<id>` and need no command file.

---

## Skills

Skills are invoked with `@<id>` (explicit) or matched by description (ambient).

| Skill           | Invocation                            | Purpose                                                                   |
|-----------------|---------------------------------------|---------------------------------------------------------------------------|
| `@spec`         | `@spec [topic]`                       | Stress-test a design through adversarial decision-tree conversation       |
| `@arch`         | `@arch TICKET`                        | Generate type-aware implementation plan → Jira comment                    |
| `@build`        | `@build`                              | Autonomous slice-by-slice TDD with per-slice commits (ad-hoc mode without a plan) |
| `@review`       | `@review`                             | Risk-routed code review vs main (HITL point in factory model)             |
| `@yagni-review` | `@yagni-review`                       | Over-engineering-only review: find what to delete, one line per finding   |
| `@debt-ledger`  | `@debt-ledger`                        | Harvest `deferred:` comments into a tracked debt ledger                   |
| `@ship`         | `@ship`                               | Checks → fresh-review gate → autosquash → push → MR; close artifacts last |
| `@codemap`      | `@codemap`                            | Generate hierarchical architectural codemap of the codebase               |
| `@learn`        | `@learn [rule]`                       | Capture a correction append-only; `@learn review` prunes and promotes     |
| `@create-skill` | `@create-skill [skill\|agent] [name]` | Guide creation of new skills and agents using research-backed checklist   |
| `@handoff`      | `@handoff [focus]`                    | Compact the session into a handoff doc + sync STATE.md for the next agent |
| `@log-hours`    | `@log-hours [YYYY-MM-DD \| yesterday]` | Draft a day's Toggl entries from history + sessions; write on approval    |

---

## Agents

Primary agents are Tab-switchable during a session. Subagents run in isolated context windows and return findings only.

| Agent                 | Trigger                                         | Purpose                                                     | Mode     |
|-----------------------|-------------------------------------------------|-------------------------------------------------------------|----------|
| `reviewer`            | `/review`, "check my changes", "review !123"    | Code review (own branch or incoming MR). Auto-detects mode. | all      |
| `observer`            | "@observer \<question\>", "@observer update"    | Maintain and explain codebase via codemaps                  | subagent |

---

## External Tools

Skills call these CLI tools when available. Install them separately.

| Tool                 | Used by                        | Purpose                               |
|----------------------|--------------------------------|---------------------------------------|
| `glab`               | `@ship`, `reviewer`            | GitLab CLI for MRs and pipelines      |
| `acli`               | `@arch`                        | Atlassian CLI for Jira                |
| `uv` / `poetry`      | `@ship`                        | Python dependency sync                |

---

## Common Patterns

**Before implementing — validate the plan:**
```
@arch TICKET
@build
```

**Before shipping — validate the pipeline:**
```
@review
@ship
```

**Capture a lesson before closing a session:**
```
@learn never use bare except clauses because they hide all errors silently
```

**Context hygiene between major steps:**
```
@arch TICKET   → /clear → @build        # fresh context for implementation
@build         → /clear → @review       # fresh context for review
@review        → /clear → @ship         # fresh context for ship
```

---

## Global Rules

Your personal global rules (identity, stack, style, model routing) live at
`global/AGENTS.md`, which is **gitignored** so those details stay off this
public repo.

```bash
cp global/AGENTS.md.example global/AGENTS.md   # redacted template → local real file
$EDITOR global/AGENTS.md                        # fill in your details
make deploy-global                              # install → ~/.config/opencode/AGENTS.md
```

`make deploy-global` writes to `~/.config/opencode/AGENTS.md`. Because
`~/.claude/CLAUDE.md` symlinks to that file, both OpenCode and Claude Code pick
it up. `make drift` diffs the deployed copy against `global/AGENTS.md`.

---

## Deployment Targets

| Command              | What it does                                                                                     |
|----------------------|--------------------------------------------------------------------------------------------------|
| `make deploy`        | Sync skills + agents + commands + global rules to OpenCode and Claude Code                       |
| `make deploy-skills` | Sync skills to OpenCode + Claude only — leaves live agents untouched                             |
| `make deploy-global` | Install `global/AGENTS.md` → `~/.config/opencode/AGENTS.md` (gitignored source; skips if absent) |
| `make drift`         | Read-only diff of the repo against every deployed location (never copies)                        |
| `make lint`          | Validate skills, agents and docs, then run the tests                                             |

---

## Adding a Skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and instructions
2. Run `make lint-skills` to validate
3. Run `make deploy`

## Adding a New Agent

1. Create `agents/<name>.md` with YAML frontmatter (`description`, `model`, `permissions`) — the agent name comes from the filename
2. Run `make lint-agents` to validate
3. Run `make deploy`

The Claude Code variant is generated at deploy time. Never hand-edit the copy in
`~/.claude/agents/` — edit the source and run `make deploy`.
