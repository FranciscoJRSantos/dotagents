---
name: yagni-review
description: >
  Review diffs for over-engineering only. Finds what to delete: reinvented
  standard library, unneeded dependencies, speculative abstractions, dead
  flexibility. One line per finding with tag and replacement. Use when the
  user says "review for over-engineering", "what can we delete", "is this
  over-engineered", "simplify review", "yagni review", or invokes
  /yagni-review. Complements correctness-focused /review — this one only
  hunts complexity.
---

# YAGNI Review

Review the current branch's work against its merge base, including the working
tree and untracked files, for unnecessary complexity. One line per finding:
location, what to cut, what replaces it. The diff's best outcome is getting
shorter.

---

## Scope

Over-engineering and complexity **only**. Correctness bugs, security holes,
and performance are explicitly out of scope — route them to `/review`.

---

## Step 1: Get the Diff

Resolve the base branch and diff from the merge base, so committed, staged,
unstaged and untracked work all appear — the same scope the `reviewer` uses:

```bash
BASE=$(git merge-base main HEAD 2>/dev/null \
  || git merge-base origin/main HEAD 2>/dev/null \
  || git merge-base master HEAD 2>/dev/null)
if [ -z "$BASE" ]; then echo "No base branch found — ask the user which to diff against."; fi

git diff "$BASE"
git diff "$BASE" --stat
git ls-files --others --exclude-standard
```

The last command lists new, untracked files — `git diff` does not show them.

---

## Step 2: Classify Findings

The tags, line format and gotchas live only in
`~/.agents/partials/yagni-rules.md`, shared with `@reviewer` — do not duplicate
them here.

```bash
cat ~/.agents/partials/yagni-rules.md
```

Assign one tag per finding. This skill lists every finding regardless of severity;
the partial's severity table only matters when `/review` folds them into its
report.

---

## Step 3: Format Output

One line per finding, in the partial's line format. For a single-file diff the
file prefix may be dropped.

---

## Step 4: Score

End with the only metric that matters:

```
net: -<N> lines possible.
```

If there is nothing to cut, say `Lean already. Ship.` and stop.

---

## Boundaries

- Scope: over-engineering and complexity only.
- Correctness bugs, security holes, performance are out of scope — route to `/review`.
- A single smoke test or `assert`-based self-check is the minimum, not bloat — never flag it.
- Does not apply the fixes, only lists them.

---

## Optional: Persist Findings

If the user wants to track deferred findings, mark them with `deferred:` comments
in the code (format: `# deferred: <ceiling>, <upgrade path>`). Then run
`/debt-ledger` to harvest them into a ledger.
