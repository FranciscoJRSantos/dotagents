---
name: log-hours
description: >
  Draft and log a day's Toggl time entries from the user's past tracking pattern and
  that day's agent sessions (Claude Code, Pi, OpenCode). Use when the user says "log
  my hours", "fill in Toggl", "what should I log for yesterday", "@log-hours".
  Proposes a draft table and writes entries only after explicit confirmation.
  Entry point: @log-hours [YYYY-MM-DD | yesterday]
---

# Log-Hours Skill

Reads the last month of Toggl entries to learn how the user tracks (projects,
descriptions, meeting cadence, day shape), reads the target day's Claude Code, Pi
and OpenCode sessions to see what was worked on, and proposes a draft. Entries are
created only after the user approves the draft.

---

## Tools

The `toggl` MCP is a Toggl **Track** (API v9) server exposing seven flat tools.

| Need | Tool | Arguments |
|---|---|---|
| auth / identity check | `toggl_get_me` | — |
| the day's entries | `toggl_list_time_entries` | `{start_date, end_date}` |
| running timer | `toggl_get_current_timer` | — |
| projects | `toggl_list_projects` | — |
| tasks | `toggl_list_tasks` | `{project_id}` |
| one draft row | `toggl_create_time_entry` | `{description, duration_minutes, start, project_id, billable, tags}` |

`start` is a full ISO 8601 datetime in UTC (`2026-11-03T09:00:00Z`). `billable`
defaults to `false`. There is no dry-run and no confirmation token: a create
writes immediately.

---

## Gotchas

- Always run `toggl_get_me` before the first read and treat an auth error as
  "authenticate", not "no data" BECAUSE the server reads `TOGGL_API_TOKEN` or
  `~/.claude/toggl/credentials`, and a missing token returns an empty read that
  looks exactly like a free day.
- Always work in UTC and show the Lisbon offset once BECAUSE Toggl stores UTC and
  the sessions' timestamps are UTC; the profile timezone is Europe/Lisbon, so
  mixing zones shifts an entry by an hour.
- Always pass `start` as a full ISO datetime with `Z` BECAUSE a bare `YYYY-MM-DD`
  is silently read as 09:00 UTC, which is the wrong hour for every block after
  the first.
- Always pass `duration_minutes`, never seconds BECAUSE that is the parameter's
  unit; a 60x slip still looks plausible in the table.
- Always pass `billable` explicitly from the history BECAUSE it defaults to
  `false`, so omitting it silently reclassifies billable work as non-billable.
- Never create entries before the user approves the draft BECAUSE a create writes
  immediately — no dry-run, no undo tool — so a wrong entry can only be fixed by
  hand in Toggl.
- Always list the target day's existing entries first and stop if any exist BECAUSE
  creating on top of them double-logs the day.
- Always widen the `toggl_list_time_entries` window to the day before and after
  and filter to the real day yourself BECAUSE `start_date`/`end_date` are
  date-only and a Lisbon evening entry can fall outside that boundary.
- Never count parallel sessions' spans as additive time BECAUSE the user runs several
  sessions at once; serialise them into non-overlapping blocks.
- Always ignore `personal-projects` sessions BECAUSE they are not work time.
- Always mark meetings inferred from history as `(assumed)` and ask about them
  BECAUSE sessions cannot show meetings and no calendar tool is available.
- Never use `task_id` unless the history shows tasks BECAUSE the user's entries
  carry only project + description; `toggl_list_tasks` is for verifying that, not
  for filling the field.
- Always read `events/15min` as well as the prompt buckets BECAUSE Claude works
  (reviews, analysis, long runs) for stretches with no human prompt, and a quiet
  prompt bucket is not an idle one; ask about every window you leave empty.
- Always round blocks to 15 minutes BECAUSE that is the granularity of the history.

---

## Step 1: Resolve the date

`yesterday` or no argument is today minus 1 day in Europe/Lisbon; otherwise use the
given `YYYY-MM-DD`. Compute from the real current date, never from memory.

## Step 2: Check auth and whether the day is empty

`toggl_get_me`, then `toggl_list_time_entries` for the day plus
`toggl_get_current_timer`. If entries already exist, show them and stop — offer to
fill only the gaps between them, and create nothing until the user picks that.

## Step 3: Learn the pattern

`toggl_list_projects`, then `toggl_list_time_entries` for the previous 30 days.
Note, per project: description style (ticket keys, meeting names, generic labels),
billable flag, recurring meetings by weekday and time, typical start/end and the
lunch gap.

## Step 4: Read the day's sessions

```bash
SKILL_DIR="${CLAUDE_SKILL_DIR:-${OPENCODE_SKILL_DIR:-}}"
if [ -z "$SKILL_DIR" ] || [ ! -f "$SKILL_DIR/sessions.py" ]; then
  for d in "$HOME/.pi/agent/skills/log-hours" "$HOME/.claude/skills/log-hours" "$HOME/.config/opencode/skills/log-hours"; do
    [ -f "$d/sessions.py" ] && SKILL_DIR="$d" && break
  done
fi
python3 -I "$SKILL_DIR/sessions.py" <YYYY-MM-DD>
```

Reads `~/.claude/projects/*/*.jsonl`, `~/.pi/agent/sessions/*/*.jsonl` and the
OpenCode session DB at `~/.local/share/opencode/opencode.db`, so a day split across
harnesses still produces one timeline. It skips `personal-projects` itself.

Prints per project: active window, first human prompts, ticket keys mentioned,
half-hour prompt buckets and 15-minute event counts (all activity, including
Claude's own work). Branch names and MR numbers in prompts identify tickets
and reviews.

## Step 5: Draft the blocks

Map work to the pattern from Step 3: ticket work to its key, MR reviews to the
user's review label, people/admin work to the non-billable internal project.
Serialise overlapping sessions, fit meetings from the weekday pattern, round to
15 minutes.

## Step 6: Present the draft and questions

Show a table (UTC start–end, minutes, project, description) with the billable /
non-billable totals, then ask about assumed meetings, work before the first
session, work after the last prompt, and the split of parallel work. Do not call
any create tool yet.

## Step 7: Confirm and create

On "go" / "yes" / "lgtm", call `toggl_create_time_entry` once per row with the
description, `duration_minutes`, `start` in UTC, `project_id` and the `billable`
flag from the pattern. On "adjust", revise and return to Step 6.

## Step 8: Report

List the created rows with their ids and the totals. State that the entries were
not re-read from Toggl, and that fixes must be made in Toggl directly.

---

## Quality Bar

A good log-hours run should:
- Never create, edit or duplicate entries without an approved draft
- Reproduce the user's own descriptions and project choices from history
- Surface every assumption as a question, not a silent guess
- Finish in at most 8 steps with one confirmation gate before any write
