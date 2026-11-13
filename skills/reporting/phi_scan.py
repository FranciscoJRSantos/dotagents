"""Scan a report for anything that looks like patient data or a raw log line.

Usage: python3 -I phi_scan.py <report-file | ->

Exits 1 and prints "line <n>: <kind>" per hit, exits 0 and prints "clean" when
nothing matches, exits 2 on a usage or file error. The output never echoes the
matched text, so a failed scan does not leak the value into the terminal log.
This is a stop signal for a human, not proof of absence: it flags patterns
(MRN, SSN, date of birth, email, phone, raw log line) and nothing more.
"""
import re
import sys

PATTERNS = (
    ("mrn", re.compile(r"\bmrn\b[\s:#=.(-]*[A-Z]{0,3}\d[\d -]{2,}\d", re.IGNORECASE)),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("dob", re.compile(
        r"\b(?:dob|date of birth|birth ?date)\b[\s:#=-]*"
        r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4})", re.IGNORECASE)),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("phone", re.compile(
        r"(?<![\d-])(?:\(\d{3}\)\s?|\d{3}[-. ])\d{3}[-. ]\d{4}(?![\d-])"
        r"|\+\d{1,3}[ -]\d{2,4}(?:[ -]\d{2,4}){2,3}")),
    ("log-line", re.compile(
        r"^\s*\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*\s+.*\b(?:DEBUG|INFO|WARN(?:ING)?|ERROR|CRITICAL|FATAL)\b"
        r"|^\s*(?:https?|h2|wss?) \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")),
)


def scan(text):
    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS:
            if pattern.search(line):
                hits.append({"line": number, "kind": kind})
    return hits


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: phi_scan.py <report-file | ->", file=sys.stderr)
        sys.exit(2)
    try:
        if sys.argv[1] == "-":
            body = sys.stdin.read()
        else:
            with open(sys.argv[1], encoding="utf-8") as fh:
                body = fh.read()
    except OSError as err:
        print(f"phi_scan: cannot read {err.filename or sys.argv[1]}", file=sys.stderr)
        sys.exit(2)
    found = scan(body)
    for hit in found:
        print(f"line {hit['line']}: {hit['kind']}")
    if found:
        sys.exit(1)
    print("clean")
