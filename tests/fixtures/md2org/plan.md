
# Plan: Org artifacts and per-work folders

Source: `.agents/artifacts/grill-org-artifacts-and-per-work-folders-decisions.md`
(D1–D11). Type: Feature (dev tooling). Branch: `feat/org-artifacts-per-work-folders`.

## User Story

As the sole reader of my agent artifacts, I want them written as Org and grouped in
one folder per piece of work, so I can read and fold them comfortably in Emacs and
archive finished work cleanly — without making the skill chain less reliable.

## Acceptance Criteria

- [ ] **AC1** `@grill-me`, `@plan`, `/review` and `@handoff` write Org via `md2org`; `org-check` passes on every file they write.
- [ ] **AC2** Work lives in `.agents/artifacts/<slug>/`; `@plan <slug>` works; `@plan PROJ-123` finds its log via `#+TICKET:`; bare `@plan` lists folders with `decisions.org` and no `plan.org`.
- [ ] **AC3** One `board.org` (TODO keywords + `:SLICE:`/`:MODE:`/`:BLOCKS:`/`:BLOCKED_BY:`/`:COMMIT:` drawer) replaces kanban and impl-progress; `@implement` derives the resume point from keywords and updates via `sed`; no `yq` in any skill.
- [ ] **AC4** `artifact-dir` follows explicit slug → branch ticket → only active folder, reopens archived matches, and emits `NONE`, `AMBIGUOUS` and the read-only `LEGACY LAYOUT` warning — all covered by tests.
- [ ] **AC5** `@ship` gates on `#+REVIEWED_HEAD:`/`#+STATUS:` and moves the folder to `archive/` after creating the MR (`-YYYYMMDD` on collision); no skill writes `status`/`closed`/`consumed_by`.
- [ ] **AC6** `/review` and `@implement` pass `ARTIFACT_DIR` to the `reviewer`, which never asks and skips plan context when unresolved.
- [ ] **AC7** Handoffs go to `<slug>/handoffs/` or fall back to `.agents/handoffs/`; `STATE.org` and `debt-ledger.org` use keywords; the free-form and `.agents/notes/` rule is in the global rules.
- [ ] **AC8** `bin/` deploys to `~/.agents/bin/` in the same manifest as `partials/`; `make deploy` and `make lint` fail without `pandoc`; scripts have pytest coverage.
- [ ] **AC9** `agents-layout.sh scan` / `reorganize [--dry-run]` implement the D10a mapping, tested on a fixture legacy `.agents/`.
- [ ] **AC10** Docs and lint reflect the new layout; `make lint` is green; no legacy artifact names remain in `skills/`, `agents/` or `commands/`.
- [ ] **AC11** Pilot: this repo is reorganised and one small piece of work runs grill → ship on the new layout.

## Technical Approach

- **Shared logic lives in `bin/`**, deployed to `~/.agents/bin/`; skills call it in
  one line instead of carrying verbatim blocks. `md2org` is the only place pandoc
  flags live (`-f gfm-gfm_auto_identifiers -t org --wrap=preserve`), `org-check` the
  only definition of a Markdown leftover, `artifact-dir` the only resolution logic,
  `slug` the only slug rule (lowercase, hyphenated, ≤40 chars on a word boundary).
- **Deploy gotcha:** `manifest-sync.sh` keeps one manifest per target and deletes
  entries missing from the current call, so `partials/` and `bin/` must be synced into
  `~/.agents/` in one call (deploy and drift) — never separately, or one deletes the
  other.
- **Skills keep producing Markdown in chat and convert on write.** The only Org
  agents write directly is `board.org` (from a template) and `STATE.org` edits, both
  followed by `org-check`.
- **Lint transition:** slice 2 replaces the `artifact-label` identity check with a
  "calls `~/.agents/bin/artifact-dir`" check over a file list; each later slice adds
  its file, so `make lint` stays green per slice. Slice 7 rewrites the `lint-docs`
  artifact-chain regex.
- **`/review <arg>`** is treated as a slug when `.agents/{artifacts,archive}/<arg>`
  exists, otherwise as a commit/branch/MR scope as today.
- Prototypes for `org-check`, `artifact-dir` and the kanban→board conversion are in
  `/tmp/pandoc-trial-scripts/` (tested during the grill; copy before `/tmp` is cleared).

## Module Interfaces

| Module | Public Interface | Test Boundaries | Layer |
|---|---|---|---|
| `bin/artifact-dir` | `artifact-dir [slug]` → stdout `ARTIFACT_DIR=…` / `REOPENED: <slug>` / `NONE` / `AMBIGUOUS: …`; stderr `LEGACY LAYOUT …` | no `.agents`, one folder, two folders, explicit slug, ticket branch, archived→reopen, legacy files present | edge |
| `bin/md2org` | `md2org <in.md> <out.org> [KEY=VAL…]`; non-zero on leftovers | no `CUSTOM_ID`, keywords on top, `CREATED` auto, fails on injected leftovers, real-artifact fixtures | edge |
| `bin/org-check` | `org-check <file.org>` → `file:line`, exit 1 | clean pass, leftovers outside blocks, ignores `#+begin_`/`#+BEGIN_` blocks | pure |
| `bin/slug` | `slug "<text>"` → lowercase hyphenated ≤40 chars, word boundary | punctuation, long titles, ticket keys | pure |
| `tests/test_bin_*.py` | pytest driving scripts via `subprocess` in `tmp_path` git repos | — | integration |
| `Makefile` | `deploy-agents`/`drift` sync `agents/partials` + `bin` together; `lint` gains pandoc check, `artifact-dir` caller check, new chain regex | `make deploy DRY_RUN=1`, `make lint` | integration |
| `skills/grill-me/SKILL.md` | writes `<slug>/decisions.org` | bash blocks in a scratch repo | ui |
| `skills/plan/SKILL.md` | `@plan <slug>\|PROJ-123\|∅`; writes `plan.org` + `board.org`; one Markdown source for ADF and Org | scratch repo, `org-check` on board | ui |
| `skills/implement/SKILL.md` | resume from keywords; `sed` updates; ad-hoc one-slice board; fixup target from `:COMMIT:`; `STATE.org` | `sed` on a fixture board | ui |
| `skills/review/SKILL.md`, `commands/review.md`, `agents/reviewer.md` | `review.org` with `REVIEWED_HEAD`/`STATUS`; passes `ARTIFACT_DIR`; slug-or-scope argument | scratch repo | ui |
| `skills/ship/SKILL.md` | grep gate; `mv` archive with collision suffix; status block removed | scratch repo | ui |
| `skills/handoff`, `skills/debt-ledger`, `global/AGENTS.md(.example)` | slug or global handoffs; `STATE.org`; `debt-ledger.org`; notes rule | scratch repo | ui |
| `AGENTS.md`, `README.md` | artifact-chain table, project-state section | `make lint-docs` | ui |
| `scripts/agents-layout.sh` | `scan <roots…>`; `reorganize <repo> [--dry-run]` | fixture legacy `.agents/` covering every D10a mapping row; dry-run leaves it untouched; open work listed | edge |

## Implementation Steps

1. `bin/` scripts and tests; deploy and drift wiring; `pandoc` check.
2. `@grill-me` and `@plan`; start the new lint check.
3. `@implement`.
4. `/review`, the `reviewer` agent and `commands/review.md`.
5. `@ship`.
6. `@handoff`, `@debt-ledger` and the global rules.
7. Docs and the remaining lint changes.
8. `scripts/agents-layout.sh`.
9. Deploy once, then pilot on this repo.

## Out of Scope

- Codemap and `@observer`; codegraph/graphify; review-partial observability; an
  active-work pointer or per-work STATE (all follow-up topics).
- Converting legacy artifacts to Org (they are reorganised only).
- Reorganising repos other than this one (done one at a time on the next visit).
- Doom config (manual task: `prettify-symbols` for `---`/`--`, `org-table-shrink`).
- `@learn`, `@codemap`, `@log-hours`, `@yagni-review`, `@create-skill`.

## Test Plan

- **Unit/integration:** pytest for all four `bin/` scripts and `agents-layout.sh`,
  using fixture `.agents/` trees, including real artifacts copied from this repo as
  pandoc fixtures.
- **Per slice:** `make lint` green; the changed skill's bash blocks executed in a
  scratch git repo. Nothing is deployed before slice 9.
- **Manual:** slice 9 pilot — `org-check` passes on every Org file the end-to-end run
  produces; the ship → archive → reopen round trip is verified by hand.

## Completeness

Every AC maps to a slice (AC1→2,4,6 · AC2→2 · AC3→3 · AC4→1 · AC5→5 · AC6→3,4 ·
AC7→6 · AC8→1 · AC9→8 · AC10→7 · AC11→9); every slice has a verification; no
circular dependencies; no TBDs.

## Modes

Slices 1–4 and 9 are `hitl` (they set interfaces, carry open design judgment, or
touch the live setup). Slices 5–8 are `afk`: nothing deploys before slice 9, so a bad
slice is a reviewable branch commit, and their behaviour is fully specified by the
grill log and/or covered by tests. `afk` drops only the approval stop — TDD, inner
reviewer, checks and the per-slice commit still run, and the branch gets a full
`/review` before `@ship`.
