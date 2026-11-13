---
name: reporting
description: >
  Turn findings or notes into a structured report and publish it to Confluence behind
  a preview, a PHI scan and an explicit confirmation. Four report types: assessment
  (BLUF), status or incident (5W1H), decision request (SCQA), architecture (arc42).
  Use when the user says "write the assessment report", "publish the findings",
  "status report", "incident report", "decision request", "architecture doc",
  "@reporting assessment".
  Entry point: @reporting <assessment|status|decision|architecture> [slug]
---

# Reporting Skill

Builds one report from the work folder's artifacts, shows it, scans it for patient data and
raw log lines, and publishes it as a child page on Confluence only after the user confirms.
Structure comes from the report type, each following an established framework. v1 has one
destination (Confluence) and never writes to Jira. For an assessment, the input is the
triaged `findings.org` that `@assess` produced.

---

## Gotchas

- Never publish before the preview, the PHI scan and the user's explicit "publish" BECAUSE a Confluence page is indexed and cached the moment it exists, and deleting it later does not unpublish it.
- Never publish when `phi_scan.py` exits 1 BECAUSE a hit means the text looks like patient data or a raw log line; remove the text and re-scan, there is no override. A false positive (a team member's email) is also fixed by editing the text.
- Never put a raw log line, payload, record identifier or data value in a report BECAUSE the audience is wider than the people cleared to see production data; cite `path:line` and totals only.
- Always carry only `ACCEPTED` and `EDITED` findings into an assessment BECAUSE the team already triaged the rest; `REJECTED` and `NEW` stay out, and `NEW` means triage is unfinished, so stop.
- Always re-run the PHI scan after any edit to `report.md` made after a passed scan BECAUSE the scan only vouches for the exact text it read; an edit at the final gate sends the report back to Step 5.
- Always write `report.md` as Markdown BECAUSE the report is posted to Confluence as converted Markdown, so it is exempt from the Org rule.
- Always resolve the Confluence parent by numeric id BECAUSE a title lookup can pick the wrong page of the same name.
- Never create a second page for a run that already has one without asking BECAUSE two pages split the comments the team and PO leave; offer to update the first instead.
- Never write to Jira or any destination other than Confluence BECAUSE v1 covers one destination; other destinations are added when a real report needs them.

---

## Step 1: Resolve the Work Folder and the Type

The first argument is the type (`assessment`, `status`, `decision` or `architecture`); an optional second argument is the work slug. Check that `pandoc` exists (`command -v pandoc`; the publish step needs it) and resolve the folder with `~/.agents/bin/artifact-dir`:

```bash
R=<this skill's own directory, next to this SKILL.md>
SLUG=<slug from the invocation, or empty>
OUT=$(~/.agents/bin/artifact-dir "$SLUG"); rc=$?
echo "$OUT"
DIR=$(printf '%s\n' "$OUT" | sed -n 's/^ARTIFACT_DIR=//p')
```

`NONE`, `AMBIGUOUS` or `NOT FOUND`: show the output and ask which slug. For `assessment`, the folder is an `assess-*` run and must hold a triaged `findings.org`:

```bash
A=<the assess skill's directory, a sibling of this skill's directory>
python3 -I "$A/findings_org.py" check "$DIR/findings.org"
```

Exit 1 means triage is unfinished: show the list and stop; the user finishes in Doom and runs `@assess triage`.

## Step 2: Gather the Inputs

- **assessment** — `findings.org` (parse the accepted ones), `.agents/system.md`, `cross-repo.org`, `preflight.org`, `log-check.org` when present, `verification.org` for open questions, and the repo SHAs:

  ```bash
  python3 -I "$A/findings_org.py" parse "$DIR/findings.org"      # JSON, keep triage ACCEPTED and EDITED
  for r in <repo path> ...; do printf '%s ' "$(basename "$r")"; git -C "$r" rev-parse --short HEAD; done
  ```

- **status** — ask for what happened, when, who is affected, why, what is being done and what is next, or read them from the work folder's `STATE.org` and handoffs.
- **decision** — ask for the situation, the complication, the question, the options and the cost of doing nothing; read the work folder's `decisions.org` when it exists.
- **architecture** — read `plan.org`, `.agents/system.md` and the code's top-level layout; ask for anything the arc42 sections need that the artifacts do not hold.

Ask only for what is missing; one question at a time.

## Step 3: Build report.md

Write `$DIR/report.md` from the template for the type. Fill every section; write "none" or "not covered" instead of deleting one. Keep it to what the reader must decide first (BLUF: the answer before the evidence).

**assessment** (BLUF / Minto pyramid, the D10 layout):

```bash
cat > "$DIR/report.md" <<'EOF'
# Tech assessment: <system> (<YYYY-MM>)

## Header
- Repos and SHAs: <repo> @ <sha>, ...
- Method: <surveys, verification, cross-repo pass, log check yes/no>
- Coverage: <repos covered, repos not cloned, coverage gaps>
- Out of scope: <what this assessment did not look at>

## Summary
<two or three sentences: the answer first>

| Repo | Status | Why |
|------|--------|-----|
| <repo> | red / amber / green | <one phrase> |

Top 5: <id> <title> (<repo>), ...

## System map
<repos and how they connect, one line each; list every doc-vs-code mismatch with path:line>

## Decisions needed
1. <decision for the meeting agenda, with the owner and the cost of waiting>

## Findings
### Tech debt
- **<id> <title>** (<repo>, owner <owner>) — <claim>. Evidence: <path:line>. Proposal: <proposal>.
### Areas of improvement
### Refactors
### Architectural gaps

## Quick wins and strategic items
### Quick wins
- <id> <title> — effort <n>, impact <n>
### Strategic
- <id> <title> — effort <n>, impact <n>

## Accepted debt and "looks bad but is fine"
- <id or title> — <why it stays>

## Open questions
- <phrased as a question for the team, with the finding id>

## Fitness functions
- <a check that would catch each recurring problem automatically>

## Changes since the last run
<NEW / RESOLVED / PERSISTING / WORSENED counts and the notable ones, or "first run">
EOF
```

**status / incident** (5W1H):

```bash
cat > "$DIR/report.md" <<'EOF'
# Status: <subject> (<date>)

## Summary
<one sentence: the current state and whether anyone must act>

## What
## Who
## When
## Where
## Why
## How (what is being done, and what comes next)
EOF
```

**decision request** (SCQA, options, cost of doing nothing):

```bash
cat > "$DIR/report.md" <<'EOF'
# Decision request: <topic>

## Recommendation
<the choice and who must make it by when>

## Situation
## Complication
## Question
## Options
| Option | Benefit | Cost | Risk |
|--------|---------|------|------|
| <A> | | | |

## Cost of doing nothing
EOF
```

**architecture** (arc42):

```bash
cat > "$DIR/report.md" <<'EOF'
# Architecture: <system>

## 1. Introduction and goals
## 2. Constraints
## 3. Context and scope
## 4. Solution strategy
## 5. Building block view
## 6. Runtime view
## 7. Deployment view
## 8. Cross-cutting concepts
## 9. Architecture decisions
## 10. Quality requirements
## 11. Risks and technical debt
## 12. Glossary
EOF
```

Replace every placeholder with content from Step 2; never leave an angle-bracket placeholder in the file.

## Step 4: Preview

Show the user the full `report.md` (or, if longer than about 15 lines, its path and the section headings with each section's first line) and ask: "Does the report read right? Say what to change, or `scan` to continue." Edit until they say `scan`.

## Step 5: PHI Scan

```bash
python3 -I "$R/phi_scan.py" "$DIR/report.md"
```

Exit 0: continue. Exit 1: show the `line <n>: <kind>` list (the scanner never prints the matched text), remove the offending text from `report.md` (open the line, replace the value with a placeholder or a count), and run the scan again. Never continue on exit 1.

## Step 6: Resolve the Destination

Read `.agents/confluence.md`; it remembers the space and the parent between runs:

```bash
cat .agents/confluence.md 2>/dev/null
```

If it exists, show it and use it. If not, find the site with `getAccessibleAtlassianResources` once, resolve the space and the "Tech Assessments" parent page to numeric ids (search Confluence by title, show the matches and ask which), then ask: "Save these to `.agents/confluence.md` for next time?" Write it only after "yes":

```bash
cat > .agents/confluence.md <<'EOF'
cloud_id: <site id or host>
space_id: <numeric space id>
parent_content_id: <numeric parent page id>
parent_title: Tech Assessments
EOF
```

## Step 7: Confirm and Publish

Convert the report to HTML (Confluence takes HTML for tables and headings) and show the final gate:

```bash
pandoc -f gfm -t html "$DIR/report.md" -o "$DIR/report.html"
```

> "Publish `<title>` as a child of `<parent_title>` in `<space>`? Scan passed. Say `publish` to create the page, anything else cancels."

Check `published.org` first: if it exists, say so in the prompt and offer update or a second page (below). Only on `publish`: read the space instructions once (`getConfluenceSpace` for the space) and the format guide once (`executeRead` with `name=getContentFormatGuide`, `inputs={toolName: "createConfluencePage"}`), then create the page:

```javascript
await tools.atlassian.createConfluenceContent({
  cloudId: "<cloud_id>",
  parent: { spaceId: "<space_id>", parentContentId: "<parent_content_id>" },
  contentType: "page",
  title: "<report title>",
  body: { format: "html", value: "<contents of report.html>" }
});
```

If the work folder already records a published page (a `published.org` file), ask whether to update it or create a second one. To update, fetch the page with `getConfluenceContent` (`detail: "full"`, `content_format: "html"`), pass its snapshot token to `updateConfluenceContent` with the new body, and re-read the page if the update returns `snapshot_stale`.

## Step 8: Record the Result

Write the page URL and time so `@assess agreed` and the next run can find it:

```bash
cat > "$DIR/published.org" <<'EOF'
#+TITLE: Published
#+CREATED: <ISO 8601 timestamp, UTC>

- Page :: <page URL>
- Type :: <report type>
- Report :: =report.md=
EOF
~/.agents/bin/org-check "$DIR/published.org"
```

Tell the user the URL and that the team and PO can now comment; for an assessment, the next step is the review meeting, then `@assess agreed` in a new session.

---

## Quality Bar

A good report should:
- Put the answer first: a reader who stops after the first screen still knows the decision needed
- Cite `path:line` for every claim about code, and contain no raw data from logs, payloads or records
- Say what it did not cover, with the reason
- Publish nothing without the preview, a clean scan and the user's explicit confirmation
