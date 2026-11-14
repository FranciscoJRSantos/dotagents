# dotagents

Research-backed agent skills and subagents for software engineering workflows.
Skills run inside OpenCode or Claude Code and are invoked with `@<skill-id>`.

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

**Certified projects (e.g. HITRUST E1):**
```
@arch TICKET → @build → @review → @ship
```
Per-slice MRs created automatically when `.agents/project.yaml` contains `certified: true`.

---

## Setup

```bash
git clone <repo>
make link   # stow skills, agents, plugins and bin/ into OpenCode, Claude Code and ~/.agents
```

`make link` regenerates the `stow/` packages (relative symlinks into the repo
sources), builds the Claude Code agent variants into `build/claude-agents/` and
runs `stow --no-folding -R`. Nothing is copied: edits to a skill, agent, plugin
or script take effect in place, so there is no deploy step and no drift. Only the
entries stow owns are touched; anything else at the destination (e.g.
`~/.claude/skills/synced/`, plugin skills, hand-made agents) is left alone.
Preview with `make link DRY_RUN=1`. An unmanaged real file that collides with a stowed name makes stow stop with a conflict; move it aside and re-run. New or deleted skills and agents need a new
`make link`; the first run also retires the old `.personal-agents-manifest` copies.

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
| `@ship`         | `@ship`                               | Checks → fresh-review gate → autosquash → push → MR; archive work folder last |
| `@create-skill` | `@create-skill [skill\|agent] [name]` | Guide creation of new skills and agents using research-backed checklist   |
| `@handoff`      | `@handoff [focus]`                    | Compact the session into a handoff doc + sync STATE.org for the next agent |
| `@log-hours`    | `@log-hours [YYYY-MM-DD \| yesterday]` | Draft a day's Toggl entries from history + sessions; write on approval    |
| `@assess`       | `@assess [system] \| triage \| agreed`  | Multi-repo tech-lead assessment: survey, verify, rank, triage             |
| `@reporting`    | `@reporting <assessment\|status\|decision\|architecture>` | Build a structured report; publish to Confluence after preview + PHI scan + confirm |

---

## Agents

Primary agents are Tab-switchable during a session. Subagents run in isolated context windows and return findings only.

| Agent                 | Trigger                                         | Purpose                                                     | Mode     |
|-----------------------|-------------------------------------------------|-------------------------------------------------------------|----------|
| `reviewer`            | `@review`, "check my changes", "review !123"    | Code review (own branch or incoming MR). Auto-detects mode. | all      |
| `assess-surveyor`     | `@assess`                                       | Read-only single-repo survey; writes `surveys/<repo>.org`   | subagent |
| `assess-verifier`     | `@assess`                                       | Blind claim check; writes `verification.org` with confidence | subagent |

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
make link                                       # link → ~/.config/opencode/AGENTS.md
```

`make link` symlinks `~/.config/opencode/AGENTS.md` to `global/AGENTS.md`. Because
`~/.claude/CLAUDE.md` symlinks to that file, both OpenCode and Claude Code pick
it up, and edits apply without a second step.

---

## Make Targets

| Command             | What it does                                                                                   |
|---------------------|------------------------------------------------------------------------------------------------|
| `make link`         | Regenerate `stow/`, build the Claude variants, stow skills + agents + plugins + bin + global rules |
| `make link DRY_RUN=1` | Preview the migration and stow commands (`stow/` and `build/` are still regenerated)                                   |
| `make build-claude` | Generate the Claude Code agent variants into `build/claude-agents/`                            |
| `make lint-links`   | Fail when a link under `stow/` does not resolve                                                |
| `make lint`         | Validate skills, agents, docs and links, then run the tests                                    |

---

## Adding a Skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`) and instructions
2. Run `make lint-skills` to validate
3. Run `make link` (new skills are not live until then)

## Adding a New Agent

1. Create `agents/<name>.md` with YAML frontmatter (`description`, `model`, `permissions`) — the agent name comes from the filename
2. Run `make lint-agents` to validate
3. Run `make link`

The Claude Code variant is generated by `make link` into `build/claude-agents/`.
Never hand-edit it — edit the source and run `make link`.
