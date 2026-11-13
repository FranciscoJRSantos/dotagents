"""Compare an @assess run with the latest earlier run (D9).

Usage: python3 -I compare_runs.py previous <run-dir>

previous prints the findings.org of the latest earlier run of the same system
(searching .agents/artifacts and .agents/archive) or exits 1 with "none".

Findings match on repo + path + kind + rule (title when the rule is empty or
"other"), never on line numbers. Tags: NEW, PERSISTING, WORSENED (priority went
up), RESOLVED (only in the earlier run). An earlier rejection is suppressed
unless the cited file changed since; then it resurfaces as NEW with
previously_rejected set. A persisting finding that was AGREED is flagged
agreed: agreed but not done.
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rank  # noqa: E402

RUN_SUFFIX = re.compile(r"-(\d{4}-\d{2})(?:-(\d+))?$")
DONE_WITHOUT_RESOLUTION = ("REJECTED",)


def _key(f):
    rule = (f.get("rule") or "").strip()
    name = f["title"] if rule.lower() in ("", "other") else rule
    return (f["repo"], f["path"], f["kind"], name.strip().lower())


def compare(prev, cur, changed):
    pool = {}
    for p in prev:
        pool.setdefault(_key(p), []).append(p)

    out = []
    for c in cur:
        matches = pool.get(_key(c))
        old = matches.pop(0) if matches else None
        tagged = dict(c)
        if old is None:
            tagged["change"] = "NEW"
        elif old.get("triage") == "REJECTED":
            if (c["repo"], c["path"]) not in changed:
                continue  # known non-issue, file untouched
            tagged["change"] = "NEW"
            tagged["previously_rejected"] = True
        else:
            tagged["change"] = "WORSENED" if rank.priority(c) > rank.priority(old) else "PERSISTING"
            if old.get("triage") == "AGREED":
                tagged["agreed"] = True
        out.append(tagged)

    for matches in pool.values():
        for old in matches:
            if old.get("triage") not in DONE_WITHOUT_RESOLUTION:
                out.append(dict(old, change="RESOLVED"))
    return out


def _order(name):
    """(YYYY-MM, fresh-run number) so -2 sorts before -10; an unsuffixed run is number 1."""
    m = RUN_SUFFIX.search(name)
    return (m.group(1), int(m.group(2) or 1))


def previous_run(cur_dir):
    cur = Path(cur_dir)
    prefix = RUN_SUFFIX.sub("", cur.name) + "-"
    pattern = re.compile(re.escape(prefix) + r"\d{4}-\d{2}(-\d+)?$")
    cur_order = _order(cur.name)
    found = []
    for root in (cur.parent, cur.parent.parent / "archive"):
        if root.is_dir():
            found += [d for d in root.iterdir()
                      if d.is_dir() and d.name != cur.name and pattern.match(d.name)
                      and _order(d.name) < cur_order and (d / "findings.org").is_file()]
    return max(found, key=lambda d: _order(d.name)) / "findings.org" if found else None


def changed_files(repo, since_iso):
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", f"--since={since_iso}", "--name-only", "--format="],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed in {repo}: {proc.stderr.strip()}")
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "previous":
        found = previous_run(sys.argv[2])
        if found is None:
            print("none")
            sys.exit(1)
        print(found)
    else:
        sys.exit(__doc__)
