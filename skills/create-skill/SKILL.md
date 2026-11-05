---
name: create-skill
description: >
  Guide the creation of a new skill or agent using the 6 research-backed OpenCode
  principles as a quality checklist. Produces a ready-to-lint SKILL.md or agent .md
  file. Use this skill whenever the user says "create a skill", "new skill", "add an
  agent", "build a slash command", "@create-skill", or wants to author a new workflow
  extension for this repo.
  Entry point: @create-skill [skill|agent] [name]
---

# Create-Skill Skill

Guides the design and creation of a new skill (invoked with `@<skill-id>`) or agent
(isolated subagent) from scratch, applying 6 research-backed principles as a checklist before
producing the draft. Nothing is written until the user explicitly approves.

---

## Gotchas

- Never write the file before Step 5 approval BECAUSE showing a draft and writing are
  separate actions — writing before approval means the user cannot course-correct the
  structure cheaply.
- Always run lint after writing BECAUSE a file that fails `make lint-skills` or
  `make lint-agents` is not deployed and will not show up in OpenCode.
- Never embed vocabulary routing frames in skills BECAUSE skills run in the main
  conversation and should stay thin; only agents need specialist frames since they
  are purpose-built for isolated analysis.
- Never suggest multi-agent designs without first applying the 45% threshold test
  BECAUSE single-agent approaches are cheaper, simpler, and usually sufficient — only
  add agents when a single agent clearly cannot reach 45% of optimal quality.
- Always place the Gotchas section before Step 1 BECAUSE context at the start of a
  skill/agent is weighted more heavily by the model than context buried mid-document
  (U-shaped attention curve — Principle 2).

---

## Step 1: Determine Type

If the user provided `skill` or `agent` inline (e.g., `@create-skill agent foo`), skip
this question and proceed with that type.

Otherwise, ask:

> "Are you creating a **skill** or an **agent**?
> - **Skill** — runs inside your main conversation as `@<skill-id>`; can write
>   artifacts; best for workflows, checklists, and orchestration.
> - **Agent** — isolated subagent with its own context window; returns findings only,
>   no artifact writes; best for file-heavy analysis that would bloat the main context."

Wait for the user's answer before proceeding.

---

## Step 2: Capture the 3 Ws

Ask the three questions below **one at a time**. If the user answers multiple at once,
accept them and skip the remaining questions.

1. **What problem does this solve?** (1–2 sentences — the core job to be done)
2. **What phrases should trigger it?** (invocations, skill id, entry point)
3. **What does it output?** (artifact with specific fields, structured findings only,
   or nothing — be specific about format)

---

## Step 3: Principle Checklist

Before generating the draft, apply these checks silently. Flag issues as inline
callouts (`> ⚠️ P2: ...`) in the draft rather than blocking questions.

| Principle | Check to apply |
|-----------|----------------|
| **P1 — Hardening** | Any step that asks the model to "format X as YAML" or "render Y as markdown" should instead provide a bash heredoc or template. Fuzzy formatting steps → deterministic bash. |
| **P2 — Context hygiene** | Keep numbered steps ≤ 15. Place critical information (Gotchas, key constraints) before Step 1, not buried mid-document. Note `/clear` boundaries if the skill produces a handoff to another skill. |
| **P5 — Institutional memory** | Gotchas must be in `Always/Never [action] BECAUSE [reason]` format. Rewrite any bare directives that lack a BECAUSE clause. |
| **P6 — Vocabulary routing** | **Agents only** — if the agent reviews/analyzes a domain (security, logic, ML metrics, CI/CD, etc.), add a specialist frame with 5–10 named anti-patterns and detection signals. Persona must be ≤ 50 tokens, no flattery, real job title. |
| **P8 — Human gate** | Place an explicit confirmation step before every file write or external API call. For agents, close with `GATE: BLOCKED` or `GATE: CLEARED`. |
| **P9 — Token economy** | Is this genuinely a single-agent task? If the user described multi-agent orchestration, apply the 45% threshold test: ask "Can a single agent reach >45% of optimal here?" If yes, collapse to single agent and explain why in the draft. Cap teams at 3–5 agents maximum if multi-agent is truly necessary. |

---

## Step 4: Draft the File

Generate the complete file content using the appropriate template below. Apply all
P1–P9 checks from Step 3 before finalising.

### Skill template

````
---
name: <name>
description: >
  <what it does — include trigger phrases and entry point on the last line>
  Entry point: @<name> [args]
---

# <Name> Skill

<2–3 sentence intro describing purpose and outcome.>

---

## Gotchas

- Always/Never [action] BECAUSE [reason]
- Always/Never [action] BECAUSE [reason]

---

## Step 1: <First action>

<prose context>

```bash
<bash commands where applicable>
```

## Step 2: ...

...

## Quality Bar

A good <name> should:
- <non-functional expectation>
- <non-functional expectation>
````

### Agent template

````
---
description: >
  <what it does — include trigger phrases; must end with "Does not write artifacts.">
model: <provider>/<model-id>
mode: subagent
permissions:
  - action: edit
    resource: "*"
    effect: deny
  - action: shell
    resource: "*"
    effect: allow
  - action: webfetch
    resource: "*"
    effect: deny
---

# <Name>

You are a <role — real job title, ≤ 50 tokens, no flattery>. Your job is to <task>.

---

## Step 1: <First action>

<prose + bash>

---

## Step N: Specialist Frame (if domain-specific)

Apply the frame only when the diff or artifact touches [relevant area].

**Vocabulary:** [domain terms]

**Named anti-patterns to detect:**
1. **<Pattern name>** — <detection signal> → <severity>
2. ...

---

## Step N+1: Return Format

<structured output template — tables, severity sections, verdict>

After the Summary section, close with exactly one of:

**GATE: BLOCKED — <reason>.**
**GATE: CLEARED — <reason>.**
````

The agent's `name` comes from its filename — never add a `name:` field. Use an
OpenCode model id (e.g. `opencode-go/qwen3.7-plus`); deploy generates the Claude
Code variant with `model: inherit` and a `tools` list derived from `permissions`.

---

## Step 5: Show Draft for Approval

Display the complete file content, then ask:

> "Does this look right? Say 'save' to write the file, or tell me what to adjust."

Do **not** write the file yet.

---

## Step 6: Write and Lint

After the user says 'save' (or 'approved', 'yes', 'lgtm'):

1. Create the directory and write the file:
   - Skill → `skills/<name>/SKILL.md`
   - Agent → `agents/<name>.md`

2. Run the appropriate lint target:

```bash
make lint-skills   # for skills
make lint-agents   # for agents
```

3. Show the lint output. If it fails, fix the frontmatter inline and re-run before
   proceeding.

---

## Step 7: Offer to Deploy

If lint passes:

> "Lint passed. Say 'deploy' to push it now, or run `make deploy` yourself."

If the user says 'deploy':
- For skills: `make deploy`
- For agents: `make deploy-agents`

Confirm the command output and the destination path.

---

## Quality Bar

A good output from this skill should:
- Have Gotchas in `Always/Never [action] BECAUSE [reason]` format — no bare directives
- Have all critical info (Gotchas, key constraints) placed before Step 1
- Have ≤ 15 numbered steps (consolidate if more are needed)
- Pass `make lint-skills` or `make lint-agents` on the first attempt
- For agents: include an OpenCode `model` id, `mode: subagent`, and a `permissions:` list (V2 schema: `action`/`resource`/`effect` rules, broad rules first because the last match wins)
- For agents with domain scope: include a specialist frame with named anti-patterns
- For any file-writing step: include a confirmation gate before the write
