"""Read and write @assess finding files (Org), check the triage, assign owners.

Usage:
  python3 -I findings_org.py check <findings.org>
  python3 -I findings_org.py parse <file.org>
  python3 -I findings_org.py claims <survey.org>...
  python3 -I findings_org.py build <run-dir> [repo=path ...]

check  exits 1 and lists every finding still NEW or REJECTED without a reason;
       otherwise prints the triage summary.
parse  prints the finding records of a survey or findings file as JSON.
claims prints only {id, repo, claim, evidence} per finding: all the verifier sees.
build  parses surveys/*.org, applies verification.org, ranks, pre-fills OWNER
       from git history (repo=path pairs) and writes findings.org.

A finding is an Org heading with a property drawer holding :ID: (see
finding-schema.md). In findings.org the TODO keyword is the triage state:
#+TODO: NEW | ACCEPTED REJECTED EDITED.
"""
import collections
import datetime
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rank as ranking  # noqa: E402

TRIAGE = ("NEW", "ACCEPTED", "REJECTED", "EDITED")
INT_FIELDS = ("impact", "interest", "effort", "confidence")
HEADING = re.compile(r"^(\*+) (?:(NEW|ACCEPTED|REJECTED|EDITED) )?(.*)$")
PROP = re.compile(r"^:([A-Z0-9_]+):\s*(.*)$")
BULLET = re.compile(r"^- (Claim|Evidence|Proposal) :: (.*)$")
PROP_ORDER = ("id", "repo", "path", "lines", "kind", "tags", "rule", "impact", "interest",
              "effort", "confidence", "owner", "reason", "group", "top5")


def _blocks(path):
    """Yield (stars, keyword, title, props, body_lines) for headings with a drawer."""
    lines = open(path, encoding="utf-8").read().splitlines()
    i = 0
    while i < len(lines):
        m = HEADING.match(lines[i])
        if not m:
            i += 1
            continue
        stars, keyword, title = m.groups()
        j = i + 1
        props = {}
        if j < len(lines) and lines[j].strip() == ":PROPERTIES:":
            j += 1
            while j < len(lines) and lines[j].strip() != ":END:":
                pm = PROP.match(lines[j])
                if pm:
                    props[pm.group(1).lower()] = pm.group(2).strip()
                j += 1
            j += 1
        body = []
        while j < len(lines) and not HEADING.match(lines[j]):
            body.append(lines[j])
            j += 1
        yield stars, keyword, title, props, body
        i = j


def parse(path):
    findings = []
    for _stars, keyword, title, props, body in _blocks(path):
        if "id" not in props:
            continue
        f = {"title": title, **props, "triage": keyword or "NEW"}
        for k in INT_FIELDS:
            if k in f and re.fullmatch(r"-?\d+", f[k]):
                f[k] = int(f[k])
        f["tags"] = f.get("tags", "").split()
        for line in body:
            bm = BULLET.match(line)
            if bm:
                f[bm.group(1).lower()] = bm.group(2).strip()
        findings.append(f)
    return findings


def validate(f):
    """Return a reason string when a finding is unusable for ranking, else ''."""
    for key in ("repo", "path", "impact", "interest", "effort"):
        if key not in f:
            return f"missing :{key.upper()}:"
    for key in ("impact", "interest", "effort"):
        if not isinstance(f[key], int) or not 1 <= f[key] <= 5:
            return f":{key.upper()}: must be an integer 1-5, got {f[key]!r}"
    return ""


def claims(paths):
    """The blind view the verifier gets: claim and evidence, nothing else."""
    return [{k: f.get(k, "") for k in ("id", "repo", "claim", "evidence")}
            for p in paths for f in parse(p)]


def write(findings, path):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = [
        "#+TITLE: Findings",
        f"#+CREATED: {now}",
        "#+TODO: NEW | ACCEPTED REJECTED EDITED",
        "",
    ]
    for f in findings:
        out.append(f"* {f.get('triage', 'NEW')} {f['title']}")
        out.append(":PROPERTIES:")
        for key in PROP_ORDER:
            value = f.get(key)
            if value in (None, "", []):
                continue
            if key == "tags":
                value = " ".join(value)
            out.append(f":{key.upper()}: {value}")
        out.append(":END:")
        for label in ("claim", "evidence", "proposal"):
            if f.get(label):
                out.append(f"- {label.capitalize()} :: {f[label]}")
        out.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def check(path):
    errors = []
    for f in parse(path):
        if f["triage"] == "NEW":
            errors.append(f"{f['id']}: still NEW — accept, edit or reject it")
        elif f["triage"] == "REJECTED" and not f.get("reason"):
            errors.append(f"{f['id']}: REJECTED without a reason — add a :REASON: property")
    return errors


def summary(path):
    return dict(collections.Counter(f["triage"] for f in parse(path)))


def owners(repo, paths):
    """Most frequent author across the git history of the given paths ('' if none)."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%an", "--", *paths],
        capture_output=True, text=True,
    )
    names = [n for n in proc.stdout.splitlines() if n]
    if proc.returncode != 0 or not names:
        return ""
    counts = collections.Counter(names)
    return sorted(counts, key=lambda n: (-counts[n], n))[0]


def apply_verification(findings, path):
    """Merge verification.org verdicts into findings and bucket them."""
    verdicts = {}
    for _s, _k, title, props, _b in _blocks(path):
        if "confidence" in props:
            verdicts[title.strip()] = props
    buckets = {"kept": [], "open": [], "dropped": [], "fine": []}
    for f in findings:
        merged = dict(f)
        v = verdicts.get(f["id"])
        if v is None:
            buckets["dropped"].append(merged)
            continue
        merged["confidence"] = int(v["confidence"])
        merged["verdict"] = v.get("verdict", "")
        buckets[ranking.bucket(merged)].append(merged)
    return buckets


def build(run_dir, repo_paths):
    parsed = []
    for survey in sorted(glob.glob(os.path.join(run_dir, "surveys", "*.org"))):
        parsed.extend(parse(survey))
    ids = collections.Counter(f["id"] for f in parsed)
    dupes = sorted(i for i, n in ids.items() if n > 1)
    if dupes:
        raise ValueError(f"duplicate finding ids across surveys: {', '.join(dupes)}")
    findings, malformed = [], []
    for f in parsed:
        reason = validate(f)
        if reason:
            malformed.append(f"{f['id']}: {reason}")
        else:
            findings.append(f)
    buckets = apply_verification(findings, os.path.join(run_dir, "verification.org"))
    ranked = ranking.rank(buckets["kept"])
    top_ids = {f["id"] for f in ranked["top5"]}
    ordered = []
    for group in ("quick_wins", "strategic", "track", "accepted"):
        for f in ranked[group]:
            f = dict(f, group=group.replace("_", "-"), triage="NEW")
            if f["id"] in top_ids:
                f["top5"] = "yes"
            repo = repo_paths.get(f["repo"])
            if repo and "owner" not in f:
                f["owner"] = owners(repo, [f["path"]])
            ordered.append(f)
    out = os.path.join(run_dir, "findings.org")
    write(ordered, out)
    if buckets["open"] or buckets["fine"]:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write("* Open questions\n")
            fh.writelines(f"- {f['id']} {f['title']} — confidence {f['confidence']}\n" for f in buckets["open"])
            fh.write("\n* Looks bad but is fine\n")
            fh.writelines(f"- {f['id']} {f['title']}\n" for f in buckets["fine"])
    return {k: len(v) for k, v in buckets.items()} | {
        "ranked": len(ordered),
        "malformed": malformed,
        "nothing_material": ranked["nothing_material"],
    }


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check" and len(sys.argv) == 3:
        errs = check(sys.argv[2])
        if errs:
            print("\n".join(errs))
            sys.exit(1)
        print(json.dumps(summary(sys.argv[2])))
    elif cmd == "parse" and len(sys.argv) == 3:
        print(json.dumps(parse(sys.argv[2])))
    elif cmd == "claims" and len(sys.argv) >= 3:
        print(json.dumps(claims(sys.argv[2:])))
    elif cmd == "build" and len(sys.argv) >= 3:
        pairs = dict(a.split("=", 1) for a in sys.argv[3:])
        print(json.dumps(build(sys.argv[2], pairs)))
    else:
        sys.exit(__doc__)
