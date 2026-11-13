"""Rank verified findings for @assess: priority, overrides, groups, caps.

Usage: python3 -I rank.py <findings.json>

Reads a JSON list of finding dicts (see finding-schema.md) and prints
{quick_wins, strategic, track, accepted, top5, nothing_material}.

priority = impact * interest / effort. Security, PHI and data-correctness
findings sort ahead of everything else. At most 15 findings per repo are
ranked; the overflow goes to Track. Findings flagged accepted_risk form their
own group and never reach the Top 5.
"""
import json
import re
import sys

OVERRIDE_TAGS = {"security", "phi", "data-correctness"}
CAP_PER_REPO = 15
TOP_N = 5
CITATION = re.compile(r"[\w./-]+:\d+")


def priority(f):
    return f["impact"] * f["interest"] / f["effort"]


def _order_key(f):
    overridden = bool(OVERRIDE_TAGS & set(f.get("tags", [])))
    return (not overridden, -priority(f), f["id"])


def bucket(f):
    """Verifier result -> kept | open | dropped | fine (D7 thresholds)."""
    if not CITATION.search(f.get("evidence", "")):
        return "dropped"
    if f.get("verdict") == "intentional":
        return "fine"
    if f.get("verdict") == "mismatch":
        return "dropped"
    confidence = f.get("confidence", 0)
    if confidence >= 80:
        return "kept"
    if confidence >= 50:
        return "open"
    return "dropped"


def rank(findings):
    accepted = [f for f in findings if f.get("accepted_risk")]
    live = sorted((f for f in findings if not f.get("accepted_risk")), key=_order_key)

    quick, strategic, track = [], [], []
    per_repo = {}
    for f in live:
        if f["impact"] < 3:
            track.append(f)
            continue
        if per_repo.get(f["repo"], 0) >= CAP_PER_REPO:
            track.append(f)
            continue
        per_repo[f["repo"]] = per_repo.get(f["repo"], 0) + 1
        (quick if f["effort"] <= 2 else strategic).append(f)

    top5 = sorted(quick + strategic, key=_order_key)[:TOP_N]
    return {
        "quick_wins": quick,
        "strategic": strategic,
        "track": track,
        "accepted": sorted(accepted, key=_order_key),
        "top5": top5,
        "nothing_material": not (quick or strategic),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: rank.py <findings.json>")
    with open(sys.argv[1]) as fh:
        print(json.dumps(rank(json.load(fh))))
