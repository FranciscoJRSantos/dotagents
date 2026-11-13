"""Commits and distinct authors per file over a time window, for @assess surveyors.

Usage: python3 -I hotspots.py <repo> [months]

Prints a JSON list of {path, commits, authors}, most-committed first. A repo
with no commits in the window (or no commits at all) prints [].
"""
import collections
import json
import subprocess
import sys

MARK = "\x1e"


def hotspots(repo, months=6) -> list:
    proc = subprocess.run(
        [
            "git", "-C", str(repo), "log",
            f"--since={months} months ago",
            "--name-only", f"--format={MARK}%an",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        if "does not have any commits yet" in proc.stderr:
            return []
        raise RuntimeError(proc.stderr.strip() or "git log failed")
    commits = collections.Counter()
    authors = collections.defaultdict(set)
    for block in proc.stdout.split(MARK)[1:]:
        author, *paths = block.split("\n")
        for path in filter(None, (p.strip() for p in paths)):
            commits[path] += 1
            authors[path].add(author)
    ranked = sorted(commits, key=lambda p: (-commits[p], p))
    return [{"path": p, "commits": commits[p], "authors": len(authors[p])} for p in ranked]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: hotspots.py <repo> [months]")
    months = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    try:
        print(json.dumps(hotspots(sys.argv[1], months)))
    except RuntimeError as err:
        sys.exit(f"hotspots: {err}")
