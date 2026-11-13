"""Two-way match of consumed vs exposed interfaces across a system, for @assess.

Usage: python3 -I interface_match.py <run-dir> [--tf <file.tf>]... [--openapi <keys.txt>]

Reads <run-dir>/surveys/*.org interface sheets (see finding-schema.md), plus
optional Terraform files and an OpenAPI key list (one "METHOD /path" per line),
and prints {unmatched_consumers, unmatched_producers, matched} as JSON.

OpenAPI wins for HTTP routes when given: a route counts as produced only if the
spec declares it, whatever the survey says. A repo never matches its own
exposures. A service-level consumer (an env var pointing at another repo) matches
any repo that exposes something.
"""
import glob
import json
import os
import re
import sys

HTTP = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(\S+)$", re.IGNORECASE)
BULLET = re.compile(r"^- =(.+?)=(?: → (\S+))?(?: \(.*?\))? — =(.+?)=\s*$")
TF_RESOURCE = re.compile(
    r'resource\s+"(aws_sqs_queue|aws_s3_bucket|aws_sns_topic|aws_dynamodb_table)"\s+"([^"]+)"\s*\{(.*?)\n\}', re.DOTALL)
TF_PREFIX = {"aws_sqs_queue": ("queue:", "name"), "aws_sns_topic": ("topic:", "name"),
             "aws_s3_bucket": ("s3://", "bucket"), "aws_dynamodb_table": ("table:", "name")}


def normalize(name):
    name = name.strip()
    m = HTTP.match(name)
    if not m:
        return name.lower().replace("_", "-")
    path = re.sub(r"\{[^}]*\}|:[A-Za-z_]\w*", "{}", m.group(2)).rstrip("/") or "/"
    return f"{m.group(1).upper()} {path.lower()}"


def is_http(name):
    return bool(HTTP.match(name.strip()))


def parse_sheet(path):
    sheet = {"exposes": [], "consumes": [], "config": []}
    in_sheet, section = False, None
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    for line in lines:
        if line.startswith("* "):
            in_sheet, section = line[2:].strip() == "Interface sheet", None
        elif in_sheet and line.startswith("** "):
            section = line[3:].strip().lower()
        elif in_sheet and section in sheet:
            m = BULLET.match(line)
            if m:
                sheet[section].append({"name": m.group(1), "cite": m.group(3), "target": m.group(2)})
    return sheet


def parse_terraform(text):
    decls = set()
    for rtype, label, body in TF_RESOURCE.findall(text):
        prefix, attr = TF_PREFIX[rtype]
        am = re.search(rf'^\s*{attr}\s*=\s*"([^"]+)"', body, re.MULTILINE)
        decls.add(prefix + (am.group(1) if am else label))
    return decls


def match(sheets, tf_decls, openapi=None):
    tf = {normalize(d) for d in tf_decls}
    spec = {normalize(k) for k in openapi} if openapi is not None else None

    def spec_governs(name):
        return spec is not None and is_http(name)

    surveyed = {}  # key -> set of repos exposing it (spec-governed HTTP excluded)
    for repo, s in sheets.items():
        for x in s["exposes"]:
            if not spec_governs(x["name"]):
                surveyed.setdefault(normalize(x["name"]), set()).add(repo)

    matched, unmatched_consumers = {}, []
    for repo, s in sheets.items():
        for c in s["consumes"]:
            key = normalize(c["name"])
            producer = None
            if spec_governs(c["name"]) and key in spec:
                producer = "openapi"
            elif surveyed.get(key, set()) - {repo}:
                producer = sorted(surveyed[key] - {repo})[0]
            elif key in tf:
                producer = "terraform"
            elif c.get("target") and c["target"] != repo and sheets.get(c["target"], {}).get("exposes"):
                producer = c["target"]
            if producer is None:
                unmatched_consumers.append({"repo": repo, "name": c["name"], "cite": c["cite"],
                                            "target": c.get("target")})
            else:
                entry = matched.setdefault((key, producer), {"name": c["name"], "producer": producer,
                                                              "consumers": []})
                if repo not in entry["consumers"]:
                    entry["consumers"].append(repo)

    consumed = {}  # key -> repos consuming it; service-level targets tracked apart
    targeted = {}
    for repo, s in sheets.items():
        for c in s["consumes"]:
            consumed.setdefault(normalize(c["name"]), set()).add(repo)
            if c.get("target"):
                targeted.setdefault(c["target"], set()).add(repo)

    unmatched_producers = []
    for repo, s in sheets.items():
        for x in s["exposes"]:
            key = normalize(x["name"])
            declared = (not spec_governs(x["name"])) or key in spec
            used = (consumed.get(key, set()) - {repo}) or (targeted.get(repo, set()) - {repo})
            if not (declared and used):
                unmatched_producers.append({"repo": repo, "name": x["name"], "cite": x["cite"]})

    return {
        "unmatched_consumers": unmatched_consumers,
        "unmatched_producers": unmatched_producers,
        "matched": sorted(matched.values(), key=lambda m: (m["name"], m["producer"])),
    }


def render(result):
    def lines(items, fmt):
        return [fmt(i) for i in items] or ["- none"]

    out = ["* Interface match", "** Unmatched consumers"]
    out += lines(result["unmatched_consumers"], lambda i: f"- ={i['name']}= ({i['repo']}) — ={i['cite']}=")
    out += ["** Unmatched producers"]
    out += lines(result["unmatched_producers"], lambda i: f"- ={i['name']}= ({i['repo']}) — ={i['cite']}=")
    out += ["** Matched"]
    out += lines(result["matched"],
                 lambda m: f"- ={m['name']}= ← {m['producer']} (consumers: {', '.join(m['consumers'])})")
    return "\n".join(out) + "\n"


def _load(run_dir, tf_files, openapi_file):
    sheets = {os.path.basename(p)[:-4]: parse_sheet(p)
              for p in sorted(glob.glob(os.path.join(run_dir, "surveys", "*.org")))}
    decls = set()
    for f in tf_files:
        with open(f, encoding="utf-8") as fh:
            decls |= parse_terraform(fh.read())
    spec = None
    if openapi_file:
        with open(openapi_file, encoding="utf-8") as fh:
            spec = {l.strip() for l in fh if l.strip()} or None  # empty spec: fall back to surveys
    return sheets, decls, spec


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    run_dir, tf_files, openapi_file = args[0], [], None
    i = 1
    while i < len(args):
        if args[i] == "--tf" and i + 1 < len(args):
            tf_files.append(args[i + 1])
        elif args[i] == "--openapi" and i + 1 < len(args):
            openapi_file = args[i + 1]
        else:
            sys.exit(__doc__)
        i += 2
    try:
        sheets, decls, spec = _load(run_dir, tf_files, openapi_file)
    except OSError as err:
        sys.exit(f"interface_match: {err.filename or err} not found")
    if not sheets:
        sys.exit(f"interface_match: no surveys in {run_dir}/surveys")
    print(json.dumps(match(sheets, decls, spec)))
