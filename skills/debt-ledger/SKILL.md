---
name: debt-ledger
description: >
  Harvest every `deferred:` comment in the codebase into a debt ledger,
  so deliberate shortcuts and deferrals get tracked instead of rotting into
  "later means never". Use when the user says "debt ledger", "@debt-ledger",
  "what did we defer", "list the shortcuts", "ponytail ledger", or "what
  did we mark to do later". One-shot report, changes nothing.
---

# Debt Ledger

Every deliberate shortcut is marked with a `deferred:` comment naming its
ceiling and upgrade path. This collects them into one ledger so a deferral
can't quietly become permanent.

---

## Step 1: Scan

Grep the repo for `deferred:` markers, skipping `node_modules`, `.git`,
and build output:

```bash
grep -rnE '(#|//) ?deferred:' . \
  --exclude-dir=node_modules \
  --exclude-dir=.git \
  --exclude-dir=dist \
  --exclude-dir=build \
  --exclude-dir=__pycache__ \
  --exclude-dir=.next \
  --exclude-dir=target
```

Each hit is one ledger row. The comment prefix keeps prose that merely
mentions the convention out of the ledger.

---

## Step 2: Parse and Format

One row per marker, grouped by file:

```
<file>:L<line>, <what was simplified>. ceiling: <the limit named>. upgrade: <the trigger to revisit>.
```

The convention is `deferred: <ceiling>, <upgrade path>`, so pull the ceiling
and the trigger straight from the comment.

If `git` is available, optionally add an owner:

```bash
git blame -L<line>,<line> --porcelain <file> | head -1
```

---

## Step 3: Flag Rot Risk

Any `deferred:` comment that names no upgrade path or trigger gets a
`no-trigger` tag — those are the ones that silently rot.

---

## Step 4: Report

```
## Deferred Debt Ledger

| File | Line | What | Ceiling | Upgrade | Owner | Status |
|------|------|------|---------|---------|-------|--------|
| app/cache.py | L42 | global lock | throughput matters | per-account locks | francisco | ok |
| lib/parser.py | L88 | naive heuristic | (no trigger) | — | — | no-trigger |

---
3 markers, 1 with no trigger.
```

If nothing found: `No deferred: debt. Clean ledger.`

---

## Step 5: Persist (optional)

If the user asks to save it, write to `.agents/artifacts/debt-ledger.md`
with YAML frontmatter:

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

```yaml
---
artifact: debt-ledger
skill: debt-ledger
created: <ISO 8601 timestamp>
status: <clean|has-items>
markers: <N>
no_trigger: <M>
---
```

---

## Boundaries

Reads and reports only, changes nothing. One-shot. Complements `@learn`
(session-level lessons) and `.agents/STATE.md` "Deferred Items" (session
deferrals) with code-level deferral tracking.
