---
name: codemap
description: >
  Generate a hierarchical architectural codemap of the codebase — a
  high-level map of every folder explaining its responsibility, design
  patterns, data flow, and integration points. Use this skill when the user
  says "codemap", "understand the codebase", "map this repo", "what's in
  this codebase", or when entering an unfamiliar repository to get oriented.
  Entry point: @codemap
---

# Codemap Skill

Generate a hierarchical codemap that documents the architectural structure
of the codebase. The output is a tree of per-folder `codemap.md` files plus
a root `codemap.md` (the "atlas") that ties it all together.

This skill is read-only — it discovers and documents, never modifies.

---

## Overview

The skill works in three phases:

1. **Scope** — detect the repo structure and decide what to map
2. **Survey** — explore each top-level folder in parallel (or ask the user
   to narrow focus if the repo is large)
3. **Document** — write per-folder `codemap.md` files, a root atlas, and the
   change-detection state that `@observer` reads

Output lives in `.agents/codemap/`:
```
.agents/codemap/
├── codemap.json      # Change-detection state (hashes of file tree)
└── codemap.md        # Root atlas — start here
```

---

## Step 1: Scope the Repository

Run a fast structural scan:

```bash
echo "=== Top-level structure ==="
ls -la

echo "=== File count ==="
find . -type f | wc -l

echo "=== Language/tech detection ==="
if [ -f package.json ]; then echo "Node.js"; fi
if [ -f pyproject.toml ] || [ -f setup.py ]; then echo "Python"; fi
if [ -f Gemfile ]; then echo "Ruby"; fi
if [ -f go.mod ]; then echo "Go"; fi
if [ -f Cargo.toml ]; then echo "Rust"; fi

echo "=== Excluded patterns ==="
# Common things to skip
echo "  node_modules/, .git/, __pycache__/, build/, dist/, .venv/, vendor/"
```

Decide whether to map everything or ask the user to narrow focus.

For repos with **>20 top-level folders**, show the folder list and ask:

> "This repo has N top-level folders. It's large — would you like to map
> everything, or focus on a subset? (e.g. `src/, lib/, core/, api/`)"
> 
> If the user specifies a subset, note it and skip the rest.

---

## Step 2: Survey Each Folder

For each top-level folder (or user-specified subset), explore its contents.
Run these in parallel for each folder:

```bash
# Per-folder exploration
echo "=== Contents of <FOLDER>/ ==="
ls -la <FOLDER>/

echo "=== File types in <FOLDER>/ ==="
find <FOLDER>/ -type f | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10

echo "=== Sub-folders in <FOLDER>/ ==="
find <FOLDER>/ -type d -maxdepth 2 | head -30
```

Read key files in each folder (not every file — pick representative ones):
- Entry points (`index.ts`, `main.py`, `app.rb`)
- Config files (`config/`, `settings.py`)
- Obvious module roots

For each folder, build a mental model of:
1. **Responsibility** — what is this folder's job in the system?
2. **Key files** — which files are the "public API" of this folder?
3. **Dependencies** — what does this folder import/use?
4. **Consumers** — what imports from this folder?
5. **Patterns** — any visible design patterns (MVC, pub/sub, repository, etc.)

---

## Step 3: Write Per-Folder Codemaps

Create `.agents/codemap/` if it doesn't exist:

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

```bash
mkdir -p .agents/codemap
```

For each surveyed folder, write `.agents/codemap/<folder>-codemap.md`:

```markdown
# <FOLDER>/ — Responsibility Summary

## Responsibility
[1-2 sentences: what this folder does and why it exists]

## Key Files
| File | Purpose |
|------|---------|
| `<filename>` | [1-line description] |

## Design Patterns
[Any named patterns visible here — MVC, observer, factory, strategy, etc.]

## Data Flow
[How data enters and exits this module]

## Integration Points
- **Depends on:** [external folders or packages]
- **Consumed by:** [other folders that import from here]
```

Use `---` dividers between sections. If a section has no meaningful content,
write `—` instead of leaving it blank.

---

## Step 4: Write the Root Atlas

Write `.agents/codemap/codemap.md` as the entry point:

```markdown
# Codebase Codemap

Generated: <ISO 8601 timestamp>
Scope: <all | subset> — <list of mapped folders>

## Folder Map

| Folder | Responsibility |
|---------|----------------|
| `<folder>/` | [1-line summary from the per-folder codemap] |

## Architecture Notes

[Any cross-cutting patterns, shared utilities, or architectural concerns
that span multiple folders — documented here so readers don't have to
cross-reference every sub-map]

## Entry Points

- **Application entry:** [e.g. `src/index.ts`, `main.py`]
- **Tests entry:** [e.g. `tests/`, `spec/`]
- **Config:** [e.g. `.env.example`, `config/`]

## Key Boundaries

[Any important boundaries: external API clients, database access layers,
authentication middleware, etc.]
```

---

## Step 5: Write the Change-Detection State

`@observer update` reads `.agents/codemap/codemap.json` to decide which folders
to re-document. Nothing used to write that file, so observer's update mode always
started from `NO_STATE`. Writing it is the final step of this skill.

Create the directory, then run the shared state block below with its output
redirected to the state file — add `> .agents/codemap/codemap.json` after the
block's closing `}`. The same block lives in `agents/observer.md`, and
`make lint-agents` fails if the two copies differ.

```bash
mkdir -p .agents/codemap
```

<!-- codemap-state-hash:begin — shared verbatim between @codemap and @observer; make lint-agents checks identity -->
```bash
{
  printf '{\n  "generated": "%s",\n  "folders": {\n' "$(date -Iseconds)"
  first=1
  for dir in */; do
    [ -d "$dir" ] || continue
    dirname=$(basename "$dir")
    hash=$(find "$dir" -type f -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/.venv/*' -not -path '*/vendor/*' | sort | xargs -r md5sum 2>/dev/null | md5sum | cut -d' ' -f1)
    [ "$first" -eq 1 ] || printf ',\n'
    first=0
    printf '    "%s": "%s"' "$dirname" "$hash"
  done
  printf '\n  }\n}\n'
}
```
<!-- codemap-state-hash:end -->

This records one hash per top-level folder. `@observer update` compares the
hashes against the tree on disk to find changed, new, and removed folders, then
refreshes only those.

---

## Quality Bar

- **Read-only** — never modify files while mapping
- **Factual** — write only what you observe; don't speculate beyond the evidence
- **Scoped** — if the repo is large, let the user narrow focus before surveying everything
- **Actionable summaries** — the folder responsibility should be specific enough to be useful,
  not generic ("utils", "helpers" — be concrete: "JWT token validation and refresh")
- **Stable references** — key files should be the canonical public API of each module,
  not one-off scripts
