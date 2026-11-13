---
name: assess
description: >
  Multi-repo tech-lead assessment. Surveys every repo of a system, verifies and ranks
  the findings (Tech Debt, Areas of Improvement, Refactors, Architectural Gaps) and
  hands them to @reporting. Use when the user says "assess the system", "tech
  assessment", "tech lead review", "survey the repos", "find tech debt across repos",
  "@assess triage" or "@assess agreed".
  Entry point: @assess [system] | @assess triage | @assess agreed
---

# Assess Skill

Runs a tech-lead review across all repos of one system as a single system: a manifest
of repos, a tool preflight, parallel read-only surveys, then (in later steps) verification,
ranking and a triage file the team discusses on Confluence. Three modes share this file:
`@assess [system]` runs the assessment, `@assess triage` checks the triaged
`findings.org`, `@assess agreed` turns agreed findings into drafts. `@assess` never
posts anything; @reporting owns every Confluence write. Detail lives in the run
folder, not in chat.

The finding and interface-sheet shapes are defined once in `finding-schema.md`, next to
this file.

---

## Gotchas

- Never install a tool or clone a repo without the user's confirmation BECAUSE the machine and the checkouts are the user's; print the command and wait.
- Always show the system map and wait for "ok" before any survey BECAUSE a wrong manifest wastes up to 13 surveys and a wrong repo list invalidates the cross-repo pass.
- Never run more than 4 surveyors at once BECAUSE each reads a whole repo and a larger fan-out exhausts the shared quota window.
- Never let a survey, finding or report contain a raw log line, payload or data value BECAUSE the output can reach Confluence and may be PHI; code and config citations only.
- Never write to a surveyed repo BECAUSE the teams have not asked for changes; everything goes under `.agents/`.
- Always resolve the run folder with `~/.agents/bin/artifact-dir` BECAUSE triage and agreed mode must find the run that run mode created, including after `/clear`.
- Always write artifacts as Org (`=path=`, `~code~`, never backticks) BECAUSE the run folder is read in Org tooling; check each file with `~/.agents/bin/org-check`.
- Never write to Jira BECAUSE ticket creation is a separate, later decision; this skill only writes local drafts.

---

## Mode: run (`@assess [system]`)

### Step 1: Resolve the System and the Run Folder

`<system>` is the argument, or the name in `.agents/system.md`, or the repo directory name. The run folder is `assess-<system>-<YYYY-MM>` (slug it with `~/.agents/bin/slug`).

```bash
SYSTEM=<system>
SLUG=assess-$(~/.agents/bin/slug "$SYSTEM")-$(date -u +%Y-%m)
OUT=$(~/.agents/bin/artifact-dir "$SLUG")
echo "$OUT"
```

- **`ARTIFACT_DIR=…`** — an earlier run of this month exists; ask "Resume it or start fresh?" and, on fresh, set `SLUG="$SLUG-2"` and re-run `artifact-dir` with it before anything else.
- **`NOT FOUND: <slug>`** — a new run. Create it:

<!-- agents-gitignore:begin — shared verbatim across every skill that writes into .agents/; make lint-agents checks identity -->
```bash
# .agents/ is agent state: ignore everything except the shared, tracked files.
mkdir -p .agents
[ -f .agents/.gitignore ] || printf '*\n!.gitignore\n!conventions.md\n!review.md\n' > .agents/.gitignore
```
<!-- agents-gitignore:end -->

```bash
DIR=.agents/artifacts/$SLUG
mkdir -p "$DIR/surveys"
```

### Step 2: Load or Draft the System Map

`.agents/system.md` is the manifest of repos and persists across runs. If it exists, show it and skip to the confirmation.

If it is missing, draft it. Sources, in this order, each read-only:

```bash
# Terraform: services, queues, buckets, databases the system declares
grep -rhE '^(resource|module) "' --include='*.tf' . 2>/dev/null | sort -u | head -80
# AWS (optional): what is actually deployed
aws ecs list-services --cluster <cluster> --output text 2>/dev/null | head -40
# glab (cross-check): project names under the group
glab repo list --group <group> 2>/dev/null | head -40
# Local checkouts next to this repo
ls -d ../*/.git 2>/dev/null
```

Classify every repo as: **cloned** (a checkout exists), **deployed, not cloned** (list it with `git clone <url> <path>`; do not run the command), or **cloned, not deployed** (flag it as a possible orphan). Draft the manifest:

```bash
cat > .agents/system.md <<'EOF'
# System: <system>

| Repo | Path | Role | Status |
|------|------|------|--------|
| <repo> | <relative path> | <one phrase: api, worker, ml-training, infra, ...> | cloned / not cloned / orphan? |

## Not cloned
- <repo>: git clone <url> <path>
EOF
```

**Confirmation gate.** Show the table and ask: "System map for `<system>` — ok to survey the cloned repos, or edit it first?" Write the file only after the user confirms, and survey nothing until they say "ok".

### Step 3: Tool Preflight

Check the tools the run needs and write `preflight.org`. Never install anything: print the command and wait.

```bash
DIR=.agents/artifacts/$SLUG
check() { command -v "$1" >/dev/null 2>&1 && echo "- OK =$1=" || echo "- MISSING =$1= :: $2"; }
{
  printf '#+TITLE: Preflight\n#+CREATED: %s\n\n* Tools\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  check git "dnf install git"
  check python3 "dnf install python3"
  check yq "dnf install yq"
  check pandoc "dnf install pandoc"
  check glab "dnf install glab"
  check terraform "see https://developer.hashicorp.com/terraform/install"
  check aws "dnf install awscli2"
} > "$DIR/preflight.org"
~/.agents/bin/org-check "$DIR/preflight.org" && cat "$DIR/preflight.org"
```

If anything is `MISSING`, show the install commands and ask: "Reply `installed` to re-check, or `skip` to continue without." On `installed`, re-run the block; on `skip`, append `* Skipped` with the tool names to `preflight.org`. Missing `terraform`, `aws` or `glab` only narrows the cross-repo pass; say so.

### Step 4: Survey the Repos

For every cloned repo in the confirmed map, start one `assess-surveyor` subagent with its repo path, repo name, output path `$DIR/surveys/<repo>.org`, the absolute path of `hotspots.py` (in this skill's own directory, next to this `SKILL.md`) and the repo's line from the system map. Run **at most 4 at a time**: start 4, start the next as each returns.

Each surveyor reads the hotspots first (`python3 -I hotspots.py <repo> 6` — commits and authors per file over 6 months), writes `surveys/<repo>.org` with findings and an interface sheet, and returns a short summary plus a `GATE:` line. A `GATE: BLOCKED` repo is listed as a coverage gap in the run summary, not retried silently.

Update `STATE.org` with `POSITION` `assess — surveyed <n>/<total> repos`, then continue to Step 5.

### Step 5: Verify the Findings

Give the verifier the claims only, never the survey files. `claims` prints `{id, repo, claim, evidence}` and nothing else (no confidence, no reasoning):

```bash
S=<this skill's own directory, next to this SKILL.md>
ls "$DIR"/surveys/*.org >/dev/null || { echo "no surveys"; exit 1; }
python3 -I "$S/findings_org.py" claims "$DIR"/surveys/*.org > "$DIR/claims.json"
```

Start one `assess-verifier` subagent with the contents of `claims.json`, each repo's path (from the system map) and the output path `$DIR/verification.org`. The verifier runs on a different model family from the surveyor and writes one heading per finding ID with `:CONFIDENCE:` and `:VERDICT:`. A finding with no heading counts as dropped.

Buckets, applied by `findings_org.py build` in Step 8: confidence ≥80 is kept, 50–79 goes to Open questions, below 50 or with no `path:line` citation is dropped (the verifier's heading is the log), and `intentional` code goes to "Looks bad but is fine". A `GATE: BLOCKED` verifier is reported to the user; do not rank unverified findings.

### Step 6: Cross-Repo Static Pass

Match what every repo consumes against what the others (or Terraform, or an OpenAPI spec) declare, in both directions. Collect the Terraform files of the system and, when a repo ships an OpenAPI spec, its route keys (the spec wins for HTTP routes):

```bash
# OpenAPI route keys, one "METHOD /path" per line (only when a spec exists)
yq '.paths | to_entries | .[] | .key as $p | .value | keys | .[] | select(test("^(get|post|put|patch|delete|head|options)$")) | upcase + " " + $p' <openapi.yaml> > "$DIR/openapi-keys.txt"
python3 -I "$S/interface_match.py" "$DIR" --tf <infra/main.tf> [--tf <more.tf>] [--openapi "$DIR/openapi-keys.txt"] > "$DIR/interface-match.json"
```

Write `cross-repo.org` from the match plus four fixed checks, in this skeleton:

```bash
cat > "$DIR/cross-repo.org" <<'EOF'
#+TITLE: Cross-repo pass
#+CREATED: <ISO 8601 timestamp, UTC>

<the Interface match section from interface_match.render(), or the JSON summarised the same way>

* Fixed checks
** API contracts
- <unmatched HTTP consumers and producers, versioning gaps, each with =repo= and =path:line=>
** Data contracts
- <queue, topic, bucket and table shapes read in one repo and written in another, each cited>
** Config and infra drift
- <env vars and resources one repo needs that Terraform or the other repos never declare>
** Shared dependencies and practices
- <same library at different majors, three styles of the same thing, a missing shared standard>
EOF
~/.agents/bin/org-check "$DIR/cross-repo.org"
```

You verify each unmatched item yourself before writing it: open the two cited lines and drop the entry if the match failed only on naming (a renamed route, a runtime-built queue name). Anything you cannot confirm goes under `* Open questions` in the same file, never as a fact. A repo with no interface sheet (a `GATE: BLOCKED` survey) is a coverage gap; name it. If `terraform` was skipped in the preflight, say the match ran without infrastructure declarations.

### Step 7: Log Check (optional, unsandboxed only)

Not yet implemented.

### Step 8: Rank and Write findings.org

One command parses the surveys, applies `verification.org`, ranks and writes `findings.org`. Pass each cloned repo as `name=path` so `OWNER` is pre-filled from git history:

```bash
python3 -I "$S/findings_org.py" build "$DIR" <repo>=<path> <repo>=<path> ...
~/.agents/bin/org-check "$DIR/findings.org"
```

Ranking is `priority = impact × interest ÷ effort`, with security, PHI and data-correctness findings first. Groups: Quick wins (impact ≥3, effort ≤2), Strategic (impact ≥3, effort ≥3), Track (impact <3 or beyond the 15-per-repo cap), Accepted (accepted risk). Each ranked finding gets `:GROUP:` and the system Top 5 gets `:TOP5: yes`. Every heading starts as `NEW`. Print the counts `build` returns and list any `malformed` findings it skipped (a bad `:IMPACT:`, a missing `:PATH:`) as coverage gaps; if `nothing_material` is true, say "nothing material found" rather than padding the list.

Tell the user to open `findings.org` in Doom, move each heading to `ACCEPTED`, `REJECTED` (with a `:REASON:`) or `EDITED`, then run `@assess triage`.

### Step 9: Compare with the Earlier Run

Not yet implemented.

### Step 10: Hand Off to @reporting

Not yet implemented.

---

## Mode: triage (`@assess triage`)

### Step 11: Check the Triage

Resolve the run folder (an explicit slug, or the only active `assess-*` folder), then check `findings.org`:

```bash
OUT=$(~/.agents/bin/artifact-dir "$SLUG"); rc=$?
DIR=$(printf '%s\n' "$OUT" | sed -n 's/^ARTIFACT_DIR=//p')
S=<this skill's own directory, next to this SKILL.md>
python3 -I "$S/findings_org.py" check "$DIR/findings.org"
```

Exit 1 lists every finding still `NEW` and every `REJECTED` finding without a `:REASON:`; show the list and stop. Exit 0 prints the triage counts (for example `{"ACCEPTED": 9, "EDITED": 2, "REJECTED": 3}`); show them and recommend @reporting to build the report. `AMBIGUOUS` or `NOT FOUND` from `artifact-dir`: show it and ask for the slug.

---

## Mode: agreed (`@assess agreed`)

### Step 12: Mark the Agreed Findings

Not yet implemented.

### Step 13: Write Drafts

Not yet implemented.

### Step 14: Archive the Run

Not yet implemented.

---

## Quality Bar

A good assessment should:
- Cover every cloned repo or list the repos it could not cover, with the reason
- Cite `path:line` for every finding and interface-sheet entry
- Stay read-only against the surveyed repos and contain no raw data from logs or payloads
- Leave every decision to the team: findings are proposals, never silently dropped without a log entry
