---
name: learn
description: >
  Capture a correction or convention from the current session, append-only, into
  the project's .agents/conventions.md. Explicit rules and detected corrections
  both land under "## Learned (unreviewed)"; @learn review prunes them into
  "## Always / Never" or promotes them to your global AGENTS.md. Use this skill
  whenever the user says "remember this", "add a rule", "don't do that again",
  "learn this", "@learn", or wants to capture a lesson from the session before
  the conversation ends.
  Entry point: @learn [rule] | @learn review
---

# Learn Skill

Captures a rule or correction from the current session into
`.agents/conventions.md` in "Always/Never [action] BECAUSE [reason]" format,
without confirmation — before the conversation ends and the lesson is lost.

`## Learned (unreviewed)` is the inbox; `@learn review` is the pruning pass that
keeps the file worth reading. Nothing is ever replaced or merged on capture, so a
bad capture is cheap to drop and a good one is never silently lost.

---

## Modes

| Invocation | What it does |
|---|---|
| `@learn <rule text>` | Append the rule to `## Learned (unreviewed)` |
| `@learn` (no text) | Ask what the rule is, then append |
| `@learn review` | Walk the unreviewed rules: keep, edit, promote to global, or drop |

---

## Proactive Triggers

In addition to explicit `@learn` invocations, capture a rule automatically when
you detect these patterns:
- User corrects the agent's approach ("no", "wrong", "actually", "that's not right", "don't do that", "I meant", "stop")
- User uses prescriptive language ("always X", "never Y", "make sure to", "we should")
- User expresses frustration about a repeated mistake or pattern
- User provides a corrected command, syntax, or workflow after the agent made an error

When one of these triggers fires, append the rule immediately — do not ask for
confirmation. Auto-capture is project-scoped only: never write to the global
rules without the user's explicit choice in `@learn review`. The user can always
revert via git (`.agents/conventions.md` is tracked).

---

## Gotchas

- Always append — never replace, merge, or reorder existing rules BECAUSE the
  unreviewed list is an information-preserving inbox and a wrong capture must stay
  cheap to drop.
- Always skip a rule that is near-identical to one already in the file BECAUSE a
  duplicate inbox is noise; the existing rule already carries the lesson.
- Always include a date and a one-line trigger context on every capture BECAUSE
  that is what makes the review pass fast — you can judge a rule by what prompted it.
- Never auto-write global rules BECAUSE they apply to every project and only the
  user can decide a lesson generalises beyond this one.
- The `## Learned (unreviewed)` heading must be top-level. Create it appending to
  the end of the file if absent — never insert it mid-document.
- A rule without a BECAUSE clause is a bare directive. Bare directives lose their
  meaning out of context. Always get the reason.

---

## Step 1: Capture the Rule

If the user invoked `@learn review`, jump to [Review Mode](#review-mode).

If the user provided rule text inline with the invocation, use it directly and
skip to Step 2.

Otherwise ask:

> "What's the rule you want to capture? (e.g. 'never use bare except clauses' or
> 'always validate input before calling external APIs')"

---

## Step 2: Get the "Why"

If the text does not include a causal phrase ("because", "so that", "since", or
similar), ask for the reason:

> "Why should this rule exist? This becomes the BECAUSE clause — the reason is what
> makes the rule durable and applicable to new situations."

Format the final rule body:
- `Always [action] BECAUSE [reason]`
- `Never [action] BECAUSE [reason]`

---

## Step 3: Append (Never Merge)

Check whether the target file already carries a near-identical rule:

```bash
grep -i "[key term]" .agents/conventions.md 2>/dev/null
```

Pick the 2–3 most distinctive terms from the rule. If an equivalent rule already
exists, say so and stop — do not add a duplicate, and do not rewrite the existing
one.

Otherwise append one bullet under `## Learned (unreviewed)`:

```markdown
- <Always/Never rule> — <YYYY-MM-DD>, <skill or branch label>: "<≤1-line trigger context>"
```

If the file or the `## Learned (unreviewed)` heading does not exist, create it
(the heading at the end of the file, top-level):

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

```bash
[ -f .agents/conventions.md ] || printf '# Conventions\n\n## Always / Never\n\n## Learned (unreviewed)\n' > .agents/conventions.md
grep -q '^## Learned (unreviewed)' .agents/conventions.md || printf '\n## Learned (unreviewed)\n' >> .agents/conventions.md
```

Use read → modify in memory → write back. Do not use `sed` for the insert.

---

## Step 4: Confirm

Show what was written:

```
Rule captured (unreviewed):
  File:  .agents/conventions.md
  Rule:  Never use bare except clauses BECAUSE they silently swallow all errors,
         making debugging impossible and hiding production failures.
```

If the list grows, mention `@learn review` as the pruning pass.

---

## Review Mode

Invoked as `@learn review`. Walk `## Learned (unreviewed)` and decide each rule's
fate. Project scope is the default; promotion to global is the user's choice.

### R1: Load the inbox

```bash
cat .agents/conventions.md 2>/dev/null
```

If the file or the `## Learned (unreviewed)` heading is absent or has no bullets,
say `Nothing unreviewed. Conventions are clean.` and stop.

### R2: Decide each rule

Present one rule at a time and ask what to do with it:

> "Unreviewed rule: <rule>. Keep, edit, promote to global, or drop?"

- **Keep** — move it to `## Always / Never`, dropping the date/context suffix so
  that section holds clean rules.
- **Edit** — let the user rewrite the rule first, then treat it as keep.
- **Promote to global** — write it to this repo's global rules source
  (`global/AGENTS.md`), then deploy it:
  ```bash
  make deploy-global
  ```
  Remove the bullet from `.agents/conventions.md` once promoted. This only works
  where the source repo is present (it holds `global/AGENTS.md`); elsewhere, show
  the rule and tell the user to add it to their global rules by hand.
- **Drop** — remove the bullet.

Apply the decisions with read → modify in memory → write back. Do not use `sed`.

### R3: Confirm

Show a summary of what happened:

```
Learned review:
  Kept:     2  (moved to ## Always / Never)
  Edited:   1
  Promoted: 1  (global/AGENTS.md → make deploy-global)
  Dropped:  1
  Remaining unreviewed: 0
```
