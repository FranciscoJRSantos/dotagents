---
name: spec
description: >
  Interview the user relentlessly about a plan or design until reaching shared
  understanding, resolving each branch of the decision tree. Produces a decision
  log artifact consumable by @arch. Invoke with "@spec [topic]".
---

# Spec Skill

Stress-test a plan or design through adversarial conversation. Walks the
decision tree depth-first, resolving dependencies between decisions one by
one. Always explores the codebase before asking a question if the answer is
knowable from code.

Produces a decision log (`.agents/artifacts/<slug>/decisions.org`) that
`@arch <slug>` consumes downstream.

---

## Conversation Density

**Conversation is routing only.** Keep conversation output to 1-3 lines per decision.
Write all detail to artifacts. The user reads conversation for decisions, drills into
artifacts for detail.

- Decision tree → artifact
- Resolved decisions → artifact
- Full rationale → artifact
- Conversation: "Decision tree written to `<path>`. N decisions resolved. Review or say 'approved'."

---

## Step 1: Gather Context

Ask the user what they want to spec:

> "What plan or design do you want me to stress-test? Share the context, a
> doc, a quick sketch, or just describe what you're thinking about."

If the user provided a topic inline (e.g. `@spec add rate limiting to the API gateway`), use that as the starting context and say you'll explore the codebase for relevant details.

If the shared context references existing code, Jira tickets, or ADRs, explore them first to ground the conversation:

```bash
# Example: explore relevant code areas
find src -type f -name '*.py' | head -20
grep -rn 'rate.limit\|throttl' src/ --include='*.py' -l
```

---

## Step 2: Build Decision Tree

From the context, identify every decision fork — the branching points where
a choice must be made. Order them by dependency: decisions that block others
appear first.

**Do not ask questions yet.** Just present the tree:

> "Here's the decision tree I see, ordered by dependency:
>
> 1. **Persistence strategy** → Where do we store rate limit counters? (blocks #2)
> 2. **Sliding window vs fixed window** → What algorithm to use? (blocks #3)
> 3. **Per-route or per-user** → What is the rate limit key? (blocks #4)
> 4. **Error response format** → What does a 429 look like?
>
> Does this tree look right? Anything missing or out of order?"

Wait for confirmation before proceeding.

---

## Step 3: Walk the Tree

For each decision node, depth-first, one at a time:

1. **Explore first** — if the decision can be resolved by reading code,
   explore the codebase. Run searches, read relevant files, and provide
   findings before asking.

2. **Pose the question with a recommendation** — never ask a bare question.
   Always include your recommended answer and reasoning:

   > "For the persistence strategy, reading `src/middleware/` I see we already
   > use Redis for session state. I'd recommend Redis with TTL-based keys —
   > it's already in our stack, no new dependency. What do you think?"

3. **Push back on vagueness** — do not accept "we'll figure it out later",
   "it depends", "we can decide that when we get there", or similar deferrals.
   If the user truly cannot decide, mark it as an open question and move on,
   but flag any downstream decisions that are blocked by it.

4. **Record the resolution** — after each decision is resolved, note the
   answer and rationale. This feeds into the final artifact.

**One question at a time.** Wait for the user's answer before moving to the
next node. If a user's answer raises new branches, add them to the tree
and ask whether to explore them now or defer.

---

## Step 4: Summarize & Confirm

Once all nodes are walked (or explicitly deferred), present the full picture in the artifact.

Ask: *"Decision log ready at `<path>`. N decisions resolved. Review or say 'approved' to save."*

---

## Step 5: Write Artifact

Only after the user explicitly approves (says "approved", "yes", "lgtm", or
similar). If they ask for changes, go back to Step 4 with revisions.

Each piece of work lives in its own folder, `.agents/artifacts/<slug>/`, and the
skill that starts the work names it for good. Generate the slug from the topic:

```bash
SLUG=$(~/.agents/bin/slug "<topic>") || SLUG=""
DIR=".agents/artifacts/$SLUG"
[ -n "$SLUG" ] || echo "NO SLUG"
for d in "$DIR" ".agents/archive/$SLUG"; do
  [ -n "$SLUG" ] && [ -e "$d" ] && echo "EXISTS: $d"
done
```

On `NO SLUG` (the topic has no letters or digits), ask for a short topic name and
regenerate. On `EXISTS`, do not overwrite blindly: show the path and ask whether to
pick a different topic name or to continue that work. To continue, move an archived
folder back with `~/.agents/bin/artifact-dir <slug>`, read its `decisions.org`, and
write the merged log (old and new decisions) back to the same path.

First make sure `.agents/` ignores its own state:

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

Write the log as Markdown and convert it with `md2org`, which runs pandoc, stamps
the `#+KEY:` keywords on top and runs `org-check`. Never write YAML frontmatter:
metadata goes in as `KEY=VAL` arguments. Set `TICKET` to the Jira key when the
specced work maps to a ticket, so `@arch <KEY>` can find this log; leave it empty
otherwise (an empty value is omitted, never written as `null`). The body has no
`# Title` line — the title is the `TITLE` keyword — so its top-level sections use
`#`:

```bash
TICKET=""   # or the Jira key, e.g. PROJ-123
~/.agents/bin/md2org - "$DIR/decisions.org" TITLE="<topic, human-readable>" TICKET="$TICKET" <<'EOF'
# Context

<what was being specced — user's original description>

# Resolved Decisions

## D1: <question>

- **Answer**: <resolved answer>
- **Rationale**: <why>
- **Informs**: <which downstream decisions this feeds into>

## D2: <question>

- **Answer**: <resolved answer>
- **Rationale**: <why>
- **Informs**: <which downstream decisions this feeds into>

# Open Questions

- <any decisions left unresolved; otherwise "None">

# Blocked Decisions

- <any decisions that couldn't be resolved because open questions blocked them; otherwise "None">

# Recommended Next Steps

- `@arch <slug>` — to create an implementation plan from resolved decisions
- Post to Jira via MCP — to turn these decisions into a ticket
EOF
```

`md2org` must exit 0 before you continue. On a non-zero exit it prints
`file:line` for each Markdown leftover and keeps the file: fix those lines in the
Markdown and run it again.

The log is local working state, not the record. Each decision must reach the
commit message of the work it drives — that is where the "why" lives on.
`@arch <slug>` (or `@arch <KEY>` via `#+TICKET:`) reads it without any Jira access.

End with a concise summary confirming the artifact was saved.

---

## Behavioral Rules

- **One question at a time** — never dump a list. Wait for answer, ask next.
- **Codebase-first** — if a decision can be resolved by reading code, explore
  before asking the user.
- **Always recommend** — never ask a bare question. Always include your
  recommended answer with reasoning.
- **Push back** — do not accept deferrals or vagueness. Only mark a decision
  as unresolved if the user genuinely cannot answer yet.
- **Follow dependencies** — if a decision blocks others, flag it. If an
  unresolved question blocks downstream decisions, note that explicitly.
- **No Jira writes** — spec produces a decision artifact, not a ticket.
  Post to Jira via MCP after the session.
- **Decisions live in commits** — the log is local working state; every resolved
  decision must reach the commit message of the work it drives.
