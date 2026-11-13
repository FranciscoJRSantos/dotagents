"""Tests for skills/assess/compare_runs.py and the repeat-run / agreed paths of findings_org."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent / "skills" / "assess"
sys.path.insert(0, str(HERE))

import compare_runs as cr  # noqa: E402
import findings_org  # noqa: E402


def f(id, title="God file", repo="api", path="a.py", kind="debt", rule="Hotspot god file",
      impact=3, interest=3, effort=2, triage="ACCEPTED", **extra):
    return {"id": id, "title": title, "repo": repo, "path": path, "kind": kind, "rule": rule,
            "impact": impact, "interest": interest, "effort": effort, "triage": triage,
            "tags": [], "lines": "1-9", **extra}


def tags(result):
    return {x["id"]: x["change"] for x in result}


def test_new_finding():
    out = cr.compare([], [f("c1")], set())

    assert tags(out) == {"c1": "NEW"}


def test_resolved_finding_comes_from_the_previous_run():
    out = cr.compare([f("p1")], [], set())

    assert tags(out) == {"p1": "RESOLVED"}


def test_persisting_finding_keeps_current_record():
    out = cr.compare([f("p1")], [f("c1")], set())

    assert tags(out) == {"c1": "PERSISTING"}


def test_worsened_when_priority_rises():
    out = cr.compare([f("p1", impact=3)], [f("c1", impact=5)], set())

    assert tags(out) == {"c1": "WORSENED"}


def test_lower_priority_is_still_persisting():
    out = cr.compare([f("p1", impact=5)], [f("c1", impact=3)], set())

    assert tags(out) == {"c1": "PERSISTING"}


def test_line_shifts_are_ignored():
    out = cr.compare([f("p1", lines="1-9")], [f("c1", lines="40-60")], set())

    assert tags(out) == {"c1": "PERSISTING"}


def test_rule_beats_title_when_set_and_title_is_the_fallback():
    same_rule = cr.compare([f("p1", title="Old wording")], [f("c1", title="New wording")], set())
    assert tags(same_rule) == {"c1": "PERSISTING"}

    by_title = cr.compare([f("p1", rule="other", title="Same")], [f("c1", rule="", title="same")], set())
    assert tags(by_title) == {"c1": "PERSISTING"}

    different = cr.compare([f("p1", rule="other", title="A")], [f("c1", rule="other", title="B")], set())
    assert tags(different) == {"p1": "RESOLVED", "c1": "NEW"}


def test_different_repo_path_or_kind_is_a_different_finding():
    base = f("p1")
    for change in ({"repo": "web"}, {"path": "b.py"}, {"kind": "arch-gap"}):
        out = cr.compare([base], [f("c1", **change)], set())
        assert tags(out) == {"p1": "RESOLVED", "c1": "NEW"}, change


def test_earlier_rejection_is_suppressed_when_the_file_did_not_change():
    out = cr.compare([f("p1", triage="REJECTED", reason="intentional")], [f("c1")], set())

    assert out == []


def test_earlier_rejection_resurfaces_when_the_cited_file_changed():
    out = cr.compare([f("p1", triage="REJECTED", reason="intentional")], [f("c1")], {("api", "a.py")})

    assert tags(out) == {"c1": "NEW"}
    assert out[0]["previously_rejected"] is True


def test_rejected_finding_that_vanished_is_not_reported_as_resolved():
    assert cr.compare([f("p1", triage="REJECTED")], [], set()) == []


def test_agreed_but_not_done_is_flagged():
    out = cr.compare([f("p1", triage="AGREED")], [f("c1")], set())

    assert tags(out) == {"c1": "PERSISTING"}
    assert out[0]["agreed"] is True


def test_duplicate_keys_pair_up_in_order():
    prev = [f("p1"), f("p2")]
    cur = [f("c1"), f("c2"), f("c3")]

    out = cr.compare(prev, cur, set())

    assert tags(out) == {"c1": "PERSISTING", "c2": "PERSISTING", "c3": "NEW"}


def test_previous_run_finds_latest_earlier_run_in_artifacts_or_archive(tmp_path):
    agents = tmp_path / ".agents"
    for where, name in (("archive", "assess-aih-2026-09"), ("archive", "assess-aih-2026-10"),
                        ("artifacts", "assess-aih-2026-11"), ("archive", "assess-other-2026-10"),
                        ("archive", "unrelated")):
        d = agents / where / name
        d.mkdir(parents=True)
        (d / "findings.org").write_text("#+TITLE: F\n")

    prev = cr.previous_run(agents / "artifacts" / "assess-aih-2026-11")

    assert prev == agents / "archive" / "assess-aih-2026-10" / "findings.org"


def test_previous_run_none_for_a_first_run(tmp_path):
    cur = tmp_path / ".agents" / "artifacts" / "assess-aih-2026-11"
    cur.mkdir(parents=True)

    assert cr.previous_run(cur) is None


def test_changed_files_since_a_date(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()

    def commit(name, date):
        env = {**os.environ, "GIT_AUTHOR_NAME": "A", "GIT_AUTHOR_EMAIL": "a@e.c",
               "GIT_COMMITTER_NAME": "A", "GIT_COMMITTER_EMAIL": "a@e.c",
               "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        (repo / name).write_text(name)
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", name], check=True, env=env)

    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    commit("old.py", "2026-01-01T00:00:00+00:00")
    commit("new.py", "2026-11-01T00:00:00+00:00")

    assert cr.changed_files(repo, "2026-06-01T00:00:00Z") == {"new.py"}


# ── findings_org integration: build --prev and AGREED ──────────────────────

def _drawer(repo, n, **extra):
    props = {"id": f"{repo}-{n:02d}", "repo": repo, "path": "a.py", "lines": "1-2", "kind": "debt",
             "tags": "maintainability", "rule": f"rule {n}", "impact": 4, "interest": 3,
             "effort": 1 + n, "confidence": 90}
    props.update(extra)
    drawer = "\n".join(f":{k.upper()}: {v}" for k, v in props.items())
    return f"** T{n}\n:PROPERTIES:\n{drawer}\n:END:\n- Claim :: c\n- Evidence :: =a.py:1= e\n- Proposal :: p\n"


def _run(tmp, name, ns, verdicts=None):
    run = tmp / name
    (run / "surveys").mkdir(parents=True)
    (run / "surveys" / "api.org").write_text("* Findings\n" + "".join(_drawer("api", n) for n in ns))
    (run / "verification.org").write_text("#+TITLE: V\n" + "".join(
        f"* api-{n:02d}\n:PROPERTIES:\n:CONFIDENCE: 90\n:VERDICT: real\n:END:\n" for n in ns))
    return run


def test_build_with_prev_tags_changes_and_suppresses_rejections(tmp_path):
    prev = _run(tmp_path, "prev", [1, 2, 3])
    findings_org.build(str(prev), {})
    prev_items = findings_org.parse(prev / "findings.org")
    triage = {"api-01": "ACCEPTED", "api-02": "REJECTED", "api-03": "ACCEPTED"}
    for item in prev_items:
        item["triage"] = triage[item["id"]]
        if item["triage"] == "REJECTED":
            item["reason"] = "intentional"
    findings_org.write(prev_items, prev / "findings.org")

    cur = _run(tmp_path, "cur", [1, 2, 4])
    counts = findings_org.build(str(cur), {}, prev=str(prev / "findings.org"))

    parsed = {p["id"]: p for p in findings_org.parse(cur / "findings.org")}
    assert parsed["api-01"]["change"] == "PERSISTING"
    assert parsed["api-04"]["change"] == "NEW"
    assert "api-02" not in parsed  # rejected earlier, file unchanged
    assert counts["resolved"] == 1 and counts["suppressed"] == 1
    changes = (cur / "changes.org").read_text()
    assert "RESOLVED" in changes and "api-03" in changes


def test_mark_agreed_moves_accepted_and_edited_only(tmp_path):
    path = tmp_path / "f.org"
    items = [{"id": "a", "title": "A", "repo": "r", "path": "p", "kind": "debt", "tags": [], "impact": 3,
              "interest": 3, "effort": 2, "triage": "ACCEPTED", "claim": "c", "evidence": "=p:1=",
              "proposal": "x"},
             {"id": "b", "title": "B", "repo": "r", "path": "p", "kind": "debt", "tags": [], "impact": 3,
              "interest": 3, "effort": 2, "triage": "EDITED", "claim": "c", "evidence": "=p:1=",
              "proposal": "x"},
             {"id": "c", "title": "C", "repo": "r", "path": "p", "kind": "debt", "tags": [], "impact": 3,
              "interest": 3, "effort": 2, "triage": "REJECTED", "reason": "no", "claim": "c",
              "evidence": "=p:1=", "proposal": "x"}]
    findings_org.write(items, path)

    marked = findings_org.mark_agreed(path, {"a": "do first", "b": ""})

    assert marked == ["a", "b"]
    parsed = {p["id"]: p for p in findings_org.parse(path)}
    assert parsed["a"]["triage"] == "AGREED" and parsed["a"]["note"] == "do first"
    assert parsed["b"]["triage"] == "AGREED"
    assert parsed["c"]["triage"] == "REJECTED"
    assert "AGREED" in path.read_text().splitlines()[2]  # the #+TODO line
    assert findings_org.check(path) == []


def test_mark_agreed_rejects_unknown_and_rejected_ids(tmp_path):
    path = tmp_path / "f.org"
    findings_org.write([{"id": "c", "title": "C", "repo": "r", "path": "p", "kind": "debt", "tags": [],
                         "impact": 3, "interest": 3, "effort": 2, "triage": "REJECTED", "reason": "no",
                         "claim": "c", "evidence": "=p:1=", "proposal": "x"}], path)

    with pytest.raises(ValueError, match="c"):
        findings_org.mark_agreed(path, {"c": ""})
    with pytest.raises(ValueError, match="zzz"):
        findings_org.mark_agreed(path, {"zzz": ""})


def test_previous_run_orders_fresh_run_suffixes_numerically(tmp_path):
    agents = tmp_path / ".agents"
    for name in ("assess-x-2026-10", "assess-x-2026-11", "assess-x-2026-11-2", "assess-x-2026-11-10"):
        d = agents / "archive" / name
        d.mkdir(parents=True)
        (d / "findings.org").write_text("#+TITLE: F\n")
    cur = agents / "artifacts" / "assess-x-2026-11-11"
    cur.mkdir(parents=True)

    assert cr.previous_run(cur).parent.name == "assess-x-2026-11-10"
    assert cr.previous_run(agents / "artifacts" / "assess-x-2026-11-3").parent.name == "assess-x-2026-11-2"


def test_changed_files_fails_loudly_on_a_bad_repo(tmp_path):
    with pytest.raises(RuntimeError, match="git log failed"):
        cr.changed_files(tmp_path / "nope", "2026-01-01T00:00:00Z")


def test_build_reports_malformed_when_kind_is_missing(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    block = _drawer("api", 1).replace(":KIND: debt\n", "")
    (run / "surveys" / "api.org").write_text("* Findings\n" + block)
    (run / "verification.org").write_text("* api-01\n:PROPERTIES:\n:CONFIDENCE: 90\n:VERDICT: real\n:END:\n")

    counts = findings_org.build(str(run), {})

    assert any("KIND" in m for m in counts["malformed"])


def test_build_warns_when_prev_is_given_without_repo_paths(tmp_path):
    prev = _run(tmp_path, "prev", [1])
    findings_org.build(str(prev), {})
    cur = _run(tmp_path, "cur", [1])

    counts = findings_org.build(str(cur), {}, prev=str(prev / "findings.org"))

    assert counts["warnings"] and "file-change detection" in counts["warnings"][0]
