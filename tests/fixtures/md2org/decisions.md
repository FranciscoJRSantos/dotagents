
## Context

Francisco reads the artifact chain mostly in Emacs and finds Org easier to read than
Markdown. Two proposals were grilled together: migrate the `.agents/` artifacts from
`.md` to `.org`, and reorganise the flat `.agents/artifacts/` directory into folders.
The grill started from a review of the current chain (`@grill-me` → `@plan` →
`@implement` → `/review` → `@ship`) and its scripted readers (`yq` on frontmatter in
`@implement` and `@ship`, `sed`/`grep` in `@plan` and `@ship`, `md_to_adf.py` for Jira).

The design was validated against real artifacts from this repo before approval — see
"Validation" below.

## Resolved Decisions

### D1: Which artifacts become Org?
- **Answer**: Org — grill decisions, plan, board, review, STATE, handoffs, debt-ledger.
  Markdown — `.agents/conventions.md` and `.agents/review.md`. Codemap (`.agents/codemap/`)
  is out of scope.
- **Rationale**: Org for what Francisco reads in Emacs; Markdown for files that are
  tracked in work repos and read by teammates on GitLab. Codemap is a separate
  subsystem (`@codemap`/`@observer`, lint-checked state hash) mostly read by agents.
  No `debt-ledger` file has ever been written, so it is a one-line path change.
- **Informs**: D2, D7, D8, D11

### D2: Merge kanban-board and impl-progress?
- **Answer**: Yes — a single `board.org` created by `@plan` and advanced by `@implement`.
  Slice state is the Org TODO keyword (`#+TODO: TODO DOING | DONE SKIPPED`); per-slice
  data lives in a property drawer (`:SLICE:`, `:MODE:`, `:BLOCKS:`, `:BLOCKED_BY:`,
  `:COMMIT:`) followed by the description and module interfaces. Use `:SLICE:`, never
  `:ID:` (reserved by org-id). Updates are deterministic `sed`, not `yq` and not the
  agent's edit tool:
  `sed -i "s/^\* [A-Z]* Slice $N:/* DONE Slice $N:/"` and
  `sed -i "/^\* [A-Z]* Slice $N:/,/^:END:/ s/^:COMMIT:.*/:COMMIT: $SHA/"`.
  `current_slice` and the hand-synced body table disappear: the resume point is the
  first `DOING` slice, else the first `TODO` whose blockers are all `DONE`. Ad-hoc mode
  writes a one-slice `board.org`.
- **Rationale**: removes duplicated state (kanban + progress frontmatter + body table)
  and the nested YAML that was the main blocker for Org; the board becomes a native
  Org kanban (column view, agenda). `sed` was preferred over the edit tool because every
  slice has an identical empty `:COMMIT:` line.
- **Informs**: D7

### D3: How is the slug chosen?
- **Answer**: The skill that starts the work names the folder, and the name never
  changes. `@grill-me <topic>` → topic slug (existing `sed`). `@plan PROJ-123` with a
  grill log whose `#+TICKET:` matches → reuse that folder. `@plan PROJ-123` without one
  → `proj-123-<summary-slug>`. Ad-hoc `@implement` → slug from the one-sentence goal,
  confirmed by the user. Slugs cap at ~40 chars on a word boundary. Ticket lookups
  always grep `#+TICKET:`, never the folder name. `@plan grill-<slug>` becomes
  `@plan <slug>`.
- **Rationale**: Francisco mostly works on `main` in personal repos, so branch-derived
  labels collide (`main-plan.md` is overwritten by every grill-mode plan).
- **Informs**: D4, D5

### D4: How do downstream skills find the active work?
- **Answer**: Derive it every time; no stored pointer. Order: explicit slug argument
  (`@implement <slug>`, `/review <slug>`, `@ship <slug>`) → ticket key in the branch
  matched against `#+TICKET:` → the only folder in `artifacts/` → ask. The `reviewer`
  subagent cannot ask, so `/review` and `@implement` pass `ARTIFACT_DIR` in its prompt;
  called without it and unresolvable, it skips plan/board context.
- **Rationale**: a pointer in STATE goes stale because only `@implement`/`@handoff`
  write it. Worktrees each get their own gitignored `.agents/`, so derivation works per
  worktree. Further automation is "software factory" territory and out of scope.
- **Informs**: D5, D6, D10b

### D5: Folder layout and file names
- **Answer**:
  ```
  .agents/
    .gitignore  conventions.md  review.md     # tracked; unchanged
    STATE.org                                 # repo-wide
    handoffs/<ts>.org                         # only sessions with no active work
    notes/                                    # standalone, non-work artifacts (D11)
    codemap/                                  # unchanged
    debt-ledger.org                           # repo-wide, if ever saved
    artifacts/<slug>/
      decisions.org  plan.org  board.org  review.org
      handoffs/<ts>.org                       # sessions on this work
    archive/<slug>/                           # same shape, moved by @ship
  ```
  `review.org` is overwritten per `/review` run, as today.
- **Rationale**: the chain is keyed by work item, so one folder per work keeps it
  together and makes archiving one `mv`. Handoffs travel with their work. Splitting
  STATE per work overlaps with board and handoffs — deferred with the factory topic.
- **Informs**: D6

### D6: Lifecycle
- **Answer**: Location is state. `@ship` runs
  `mv .agents/artifacts/<slug> .agents/archive/<slug>` right after creating the MR
  (suffix `-YYYYMMDD` on collision); its `status: closed` sed block is deleted.
  Resolution steps 1–2 (explicit slug, branch ticket) also search `archive/` and move a
  match back with a `REOPENED:` notice; step 3 never looks there. `status`, `closed` and
  `consumed_by` are dropped — "planned" means the folder has `plan.org`, and bare
  `@plan` lists folders with `decisions.org` but no `plan.org`. Abandoned grill logs
  are archived by hand.
- **Rationale**: no skill observes MR merges, and MR feedback produces more fixups on
  the same branch, so archive-at-ship plus reopen-on-lookup covers the round trip.
  Fixes the current gap where `@ship` never closes the review artifact.
- **Informs**: D7

### D7: Org metadata format
- **Answer**: Uppercase `#+KEY: value` keywords at the top, read with
  `grep -m1 '^#+KEY:' | cut -d' ' -f2`. No file-level property drawer.
  | File | Keywords |
  |---|---|
  | all | `#+TITLE:`, `#+CREATED:` |
  | decisions, plan | `#+TICKET:` (omitted, never `null`, when absent) |
  | board | `#+TODO: TODO DOING \| DONE SKIPPED` |
  | review | `#+REVIEWED_HEAD:`, `#+STATUS: clean\|has-findings` |
  | STATE | `#+UPDATED:`, `#+BRANCH:`, `#+POSITION:` |
  Dropped: `artifact`, `skill`, the plan's `status: posted`. Optional:
  `#+JIRA_COMMENT: <url>` on the plan.
- **Rationale**: only three fields are machine-read (`ticket` by `@plan`,
  `reviewed_head` and `status` by `@ship`); keywords are one `grep`, drawers would need
  `emacs --batch`.

### D8: Markdown-drift guard and conversion
- **Answer**: Models always write Markdown; `pandoc` converts it:
  `pandoc -f gfm-gfm_auto_identifiers -t org --wrap=preserve in.md -o out.org`, then the
  `#+KEY:` header is prepended. No style partial. A backstop `org-check` (awk) flags
  Markdown leftovers outside `#+begin_`/`#+end_` blocks (case-insensitive): ``` fences,
  `^#{1,6} ` headings (silent comments in Org), `**bold**`, `](http` links, `` `code` ``.
  It runs after every Org write and after direct edits (`@implement` board updates,
  STATE updates) and must pass before the skill continues. Chat output, the `reviewer`'s
  report and plan approval stay Markdown; conversion happens on write.
- **Rationale**: Francisco cannot tell whether a model follows a loaded partial; a tool
  call is visible in the transcript and its failure is loud. Models write Markdown more
  reliably than Org. The `reviewer` must stay Markdown because its report also goes to
  GitLab MRs.
- **Informs**: D9, D10b

### D9: Jira posting of the plan
- **Answer**: Resolved by D8 — one Markdown source feeds `md_to_adf.py` (Jira comment)
  and `md2org` (`plan.org`).
- **Rationale**: no double write, no drift between Jira and the local plan.

### D10a: Migration of existing artifacts
- **Answer**: `scripts/agents-layout.sh` in the repo with two modes.
  `scan <roots…>` lists every `.agents/` on the legacy layout (any file directly under
  `artifacts/` or `handoffs/`, or a `STATE.md`) with counts and open work (status not
  `closed`/`complete`) — the migration checklist.
  `reorganize <repo> [--dry-run]` files by name, without converting:
  | Legacy | New |
  |---|---|
  | `<label>-{plan,kanban-board,impl-progress,review-impl}.md` | `archive/<label>/{plan,kanban-board,impl-progress,review}.md` |
  | `grill-<slug>-decisions.md` | `archive/<slug>/decisions.md` |
  | `<TICKET>-<rest>.md` (any other ticket-prefixed file) | `archive/<TICKET>/<rest>.md` |
  | anything else (drafts, reports, `.png`, subfolders) | `archive/misc/`, names unchanged |
  | `handoffs/*.md`, `STATE.md` | `archive/handoffs/`, `archive/STATE.md` |
  Safety net: `artifact-dir` prints a read-only `LEGACY LAYOUT: run
  scripts/agents-layout.sh reorganize .` warning; it never moves files itself.
  Repos are reorganised one at a time, on the next visit; new skills ignore legacy files
  so nothing breaks in between.
- **Rationale**: 24 `.agents/` dirs under `~/Documents` (~280 artifacts, ~70 handoffs;
  one repo alone has 118). ~220 match the chain naming. A dry-run-first
  explicit script is safer than lazy migration inside the resolver, which could archive
  live work silently.
- **Informs**: D10c

### D10b: Delivery of the shared logic
- **Answer**: A `bin/` directory in this repo, deployed by `make deploy` to
  `~/.agents/bin/` alongside partials:
  - `artifact-dir [slug]` → prints `ARTIFACT_DIR=…`, `REOPENED: …`, `NONE` (no work at
    all, so `@implement` can enter ad-hoc mode), `AMBIGUOUS: …`, or `LEGACY LAYOUT`.
  - `md2org <in.md> <out.org> KEY=VAL…` → pandoc with the tested flags, prepends
    keywords, runs `org-check`, exits non-zero on leftovers.
  - `org-check <file.org>` → the backstop alone, for direct edits.
  pytest coverage in `tests/` with sample `.agents/` folders. The `artifact-label`
  verbatim-block lint is replaced by a lint that skills call the scripts. `make deploy`
  and `make lint` fail early if `pandoc` is missing. `agents-gitignore` stays a
  verbatim block (short, must work before anything is installed).
- **Rationale**: the shared logic grew to ~40 lines used by up to 7 skills; ~15
  verbatim copies would bloat every skill the model reads. Tests are a stronger
  guarantee than identity checks.
- **Informs**: D10c

### D10c: Rollout order and docs
- **Answer**: Build everything on a branch and run `make deploy` once at the end (an
  old `@implement` cannot read a new `board.org`, so the chain must switch together).
  Slice order: (1) `bin/` scripts + tests → (2) `@grill-me`, `@plan` → (3) `@implement`
  → (4) `/review` + `reviewer` + `commands/review.md` → (5) `@ship` → (6) `@handoff`,
  `@debt-ledger`, `global/AGENTS.md.example` + `global/AGENTS.md` (notes rule) →
  (7) `AGENTS.md` artifact-chain table and project-state section, `README` skill table,
  lint → (8) `scripts/agents-layout.sh`. Post-deploy pilot on this repo: `scan`,
  `reorganize --dry-run`, `reorganize`, then one small end-to-end grill → ship run.
  Then personal repos, then work repos, each on its next visit.
- **Rationale**: deploy is explicit, so the old deployed skills can plan and implement
  their own replacement as long as nothing is deployed mid-way.

### D11: Free-form artifacts
- **Answer**: Work-scoped extras (ticket snapshots, yagni reviews, runtime numbers,
  MR/Jira/Confluence drafts) live in `artifacts/<slug>/` under free names and archive
  with the work. Standalone documents (business cases, reports, notes) live in
  `.agents/notes/`, outside the lifecycle. Format follows D1: Org via `md2org`, except
  drafts destined for Confluence, Jira or MR descriptions, which stay `.md`. The rule
  lives in the global `AGENTS.md` because no skill writes these; a loose file dropped
  into `artifacts/` trips the `LEGACY LAYOUT` warning, so violations are visible.
- **Rationale**: ~60 legacy files are free-form, written ad hoc into the flat
  `artifacts/` directory with no rule for where they belong.

## Validation

Run on 2026-11-06 against this repo's artifacts (trial files in `/tmp/pandoc-trial*`):
- pandoc 3.7.0.2 (system) and 3.9 produce identical output for `main-plan`.
- Default `-f gfm` adds 42 `:CUSTOM_ID:` drawers across 5 files; `-f gfm-gfm_auto_identifiers` removes all of them.
- Converted plan, grill log, review, handoff and STATE: headings, lists, bold, inline code, nested `#+begin_src` blocks and tables all correct; 0 backstop hits.
- The original one-line `grep` backstop false-positived on shell comments and backticks inside source blocks → replaced by the awk version that skips blocks.
- `board.org` built from the real 7-slice `main-kanban-board`; the `sed` update changed only Slice 2's keyword and `:COMMIT:`.
- `artifact-dir` mock: no `.agents`, one active folder, two active, explicit slug, ticket branch, archived-then-reopened — all correct.
- Known wart: pandoc's org writer always emits `—` as `---` and `–` as `--` (no flag disables it); handled on the Emacs display side, not by rewriting files.
- Wide tables pad every row to the widest cell (same unreadability as Markdown in Emacs); handled with `org-table-shrink`.

## Open Questions

- `personal-stack` `feat-personal-feed` (status `in_progress`): finish it with the old
  skills before deploy, or convert it by hand into the new layout during the pilot.
  Non-blocking — decide at pilot time.

## Blocked Decisions

- None

## Manual Tasks (outside this repo)

- Doom config: `prettify-symbols` mapping `"---"` → `—` (and `"--"` → `–`) in
  org-mode; `org-table-shrink` for wide tables.
- Remove `/tmp/pandoc-trial` and `/tmp/pandoc-trial-scripts` when no longer needed
  (the latter holds the tested `org_check.sh`, `artifact_dir.sh` and
  `kanban_to_board.py` prototypes, useful as slice 1 starting points).

## Follow-up Topics (separate grill sessions)

- Codemap vs codegraph/graphify for cheaper, token-efficient code search by agents.
- Observability of review partials: make it visible whether a model applied them
  (e.g. the report lists which rule sections it ran).
- "Software factory" automation: an active-work pointer, per-work STATE.

## Recommended Next Steps

- `@plan org-artifacts-and-per-work-folders` (today's syntax:
  `@plan grill-org-artifacts-and-per-work-folders`).
- Create a branch first (D10c: build on a branch, deploy once).
- Each decision must reach the commit message of the slice it drives.
