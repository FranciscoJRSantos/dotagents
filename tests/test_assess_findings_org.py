"""Tests for skills/assess/findings_org.py: write, parse, check, owners, verification."""

import os
import pytest
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "skills" / "assess"
sys.path.insert(0, str(HERE))

import findings_org  # noqa: E402

ORG_CHECK = Path.home() / ".agents" / "bin" / "org-check"


def finding(id="r-01", **kw):
    base = {
        "id": id,
        "title": "God file in routes",
        "repo": "r",
        "path": "app/routes.py",
        "lines": "10-90",
        "kind": "debt",
        "tags": ["maintainability"],
        "rule": "Hotspot god file",
        "impact": 4,
        "interest": 3,
        "effort": 2,
        "confidence": 85,
        "claim": "routes.py mixes five responsibilities.",
        "evidence": "=app/routes.py:10= defines auth, billing and export handlers.",
        "proposal": "Split by resource.",
        "triage": "NEW",
        "owner": "Ana",
    }
    base.update(kw)
    return base


def test_round_trip(tmp_path):
    path = tmp_path / "findings.org"
    original = [finding("r-01"), finding("r-02", tags=["security", "phi"], triage="ACCEPTED")]

    findings_org.write(original, path)
    parsed = findings_org.parse(path)

    assert [p["id"] for p in parsed] == ["r-01", "r-02"]
    assert parsed[1]["tags"] == ["security", "phi"]
    assert parsed[1]["triage"] == "ACCEPTED"
    assert parsed[0]["impact"] == 4
    assert parsed[0]["owner"] == "Ana"
    assert parsed[0]["claim"] == original[0]["claim"]
    assert parsed[0]["title"] == "God file in routes"


def test_written_file_has_todo_header_one_heading_per_finding(tmp_path):
    path = tmp_path / "findings.org"
    findings_org.write([finding("r-01"), finding("r-02")], path)
    text = path.read_text()

    assert "#+TODO: NEW | ACCEPTED REJECTED EDITED" in text
    assert text.count("\n* NEW ") == 2
    assert ":TRIAGE:" not in text  # the keyword is the triage state


@pytest.mark.skipif(not ORG_CHECK.exists(), reason="org-check not installed")
def test_written_file_passes_org_check(tmp_path):
    path = tmp_path / "findings.org"
    findings_org.write([finding()], path)

    proc = subprocess.run([str(ORG_CHECK), str(path)], capture_output=True, text=True)

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_check_flags_new_left_over(tmp_path):
    path = tmp_path / "f.org"
    findings_org.write([finding("r-01", triage="ACCEPTED"), finding("r-02", triage="NEW")], path)

    errors = findings_org.check(path)

    assert len(errors) == 1
    assert "r-02" in errors[0] and "NEW" in errors[0]


def test_check_flags_rejected_without_reason(tmp_path):
    path = tmp_path / "f.org"
    findings_org.write([finding("r-01", triage="REJECTED")], path)

    errors = findings_org.check(path)

    assert len(errors) == 1
    assert "r-01" in errors[0] and "reason" in errors[0].lower()


def test_check_accepts_rejected_with_reason(tmp_path):
    path = tmp_path / "f.org"
    findings_org.write([finding("r-01", triage="REJECTED", reason="Intentional, see ADR 4")], path)

    assert findings_org.check(path) == []


def test_check_clean_summary(tmp_path):
    path = tmp_path / "f.org"
    findings_org.write(
        [finding("a", triage="ACCEPTED"), finding("b", triage="EDITED"),
         finding("c", triage="REJECTED", reason="no")],
        path,
    )

    assert findings_org.check(path) == []
    assert findings_org.summary(path) == {"ACCEPTED": 1, "EDITED": 1, "REJECTED": 1}


def test_cli_check_exit_codes(tmp_path):
    bad = tmp_path / "bad.org"
    good = tmp_path / "good.org"
    findings_org.write([finding(triage="NEW")], bad)
    findings_org.write([finding(triage="ACCEPTED")], good)

    run = lambda p: subprocess.run(  # noqa: E731
        [sys.executable, "-I", str(HERE / "findings_org.py"), "check", str(p)],
        capture_output=True, text=True,
    )

    assert run(bad).returncode == 1
    ok = run(good)
    assert ok.returncode == 0
    assert "ACCEPTED" in ok.stdout


def test_parse_survey_findings_at_level_two(tmp_path):
    survey = tmp_path / "s.org"
    survey.write_text(
        "#+TITLE: Survey: r\n\n* Summary\nok\n\n* Findings\n"
        "** Swallowed errors in worker\n:PROPERTIES:\n:ID: r-01\n:REPO: r\n"
        ":PATH: w.py\n:LINES: 3-9\n:KIND: debt\n:TAGS: reliability\n:RULE: Swallowed errors\n"
        ":IMPACT: 3\n:INTEREST: 2\n:EFFORT: 1\n:CONFIDENCE: 70\n:END:\n"
        "- Claim :: Errors are ignored.\n- Evidence :: =w.py:3= bare except\n- Proposal :: Log and raise.\n"
        "\n* Interface sheet\n** Exposes\n- =GET /x= — =a.py:1=\n"
    )

    parsed = findings_org.parse(survey)

    assert len(parsed) == 1
    assert parsed[0]["title"] == "Swallowed errors in worker"
    assert parsed[0]["effort"] == 1
    assert parsed[0]["tags"] == ["reliability"]
    assert parsed[0]["proposal"] == "Log and raise."


def test_owners_returns_most_frequent_author_for_paths(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def commit(author, name):
        env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": "a@e.c",
               "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": "a@e.c"}
        (repo / name).write_text(str(os.urandom(4)))
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "c"], check=True, env=env)

    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    commit("Ana", "a.py")
    commit("Bruno", "a.py")
    commit("Bruno", "a.py")
    commit("Ana", "other.py")

    assert findings_org.owners(repo, ["a.py"]) == "Bruno"
    assert findings_org.owners(repo, ["missing.py"]) == ""


def test_apply_verification_buckets_and_updates_confidence(tmp_path):
    ver = tmp_path / "verification.org"
    ver.write_text(
        "#+TITLE: Verification\n\n"
        "* r-01\n:PROPERTIES:\n:CONFIDENCE: 90\n:VERDICT: real\n:END:\nconfirmed\n"
        "* r-02\n:PROPERTIES:\n:CONFIDENCE: 60\n:VERDICT: real\n:END:\nunsure\n"
        "* r-03\n:PROPERTIES:\n:CONFIDENCE: 20\n:VERDICT: mismatch\n:END:\ncode differs\n"
        "* r-04\n:PROPERTIES:\n:CONFIDENCE: 95\n:VERDICT: intentional\n:END:\nADR 4\n"
    )
    items = [finding(f"r-0{i}", confidence=50) for i in range(1, 5)]

    buckets = findings_org.apply_verification(items, ver)

    assert [x["id"] for x in buckets["kept"]] == ["r-01"]
    assert buckets["kept"][0]["confidence"] == 90
    assert [x["id"] for x in buckets["open"]] == ["r-02"]
    assert [x["id"] for x in buckets["dropped"]] == ["r-03"]
    assert [x["id"] for x in buckets["fine"]] == ["r-04"]


def test_apply_verification_unverified_finding_is_dropped(tmp_path):
    ver = tmp_path / "verification.org"
    ver.write_text("#+TITLE: Verification\n")

    buckets = findings_org.apply_verification([finding("r-09")], ver)

    assert [x["id"] for x in buckets["dropped"]] == ["r-09"]


def _survey(repo, n, **extra):
    props = {"id": f"{repo}-{n:02d}", "repo": repo, "path": "a.py", "lines": "1-2", "kind": "debt",
             "tags": "security" if n == 1 else "maintainability", "rule": "x",
             "impact": 4, "interest": 3, "effort": 1 + n, "confidence": 70}
    props.update(extra)
    drawer = "\n".join(f":{k.upper()}: {v}" for k, v in props.items())
    return (f"** Title {repo} {n}\n:PROPERTIES:\n{drawer}\n:END:\n"
            f"- Claim :: c\n- Evidence :: =a.py:1= e\n- Proposal :: p\n")


def test_build_writes_ranked_findings_org(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    (run / "surveys" / "r.org").write_text(
        "#+TITLE: Survey: r\n\n* Findings\n" + _survey("r", 1) + _survey("r", 2) + _survey("r", 3))
    (run / "verification.org").write_text(
        "#+TITLE: V\n\n"
        "* r-01\n:PROPERTIES:\n:CONFIDENCE: 90\n:VERDICT: real\n:END:\n"
        "* r-02\n:PROPERTIES:\n:CONFIDENCE: 65\n:VERDICT: real\n:END:\n"
        "* r-03\n:PROPERTIES:\n:CONFIDENCE: 30\n:VERDICT: mismatch\n:END:\n")

    counts = findings_org.build(str(run), {})

    assert counts["kept"] == 1 and counts["open"] == 1 and counts["dropped"] == 1
    parsed = findings_org.parse(run / "findings.org")
    assert [p["id"] for p in parsed] == ["r-01"]
    assert parsed[0]["triage"] == "NEW" and parsed[0]["top5"] == "yes"
    assert "r-02" in (run / "findings.org").read_text()  # under Open questions
    if ORG_CHECK.exists():  # the standalone org-check test above reports its own skip
        proc = subprocess.run([str(ORG_CHECK), str(run / "findings.org")], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_claims_exposes_only_claim_and_evidence(tmp_path):
    survey = tmp_path / "s.org"
    survey.write_text("* Findings\n" + _survey("r", 1, confidence=99))

    out = findings_org.claims([survey])

    assert out == [{"id": "r-01", "repo": "r", "claim": "c", "evidence": "=a.py:1= e"}]


def test_build_skips_malformed_findings_and_reports_them(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    (run / "surveys" / "r.org").write_text(
        "* Findings\n" + _survey("r", 1) + _survey("r", 2, effort=0) + _survey("r", 3, impact="high"))
    (run / "verification.org").write_text(
        "".join(f"* r-0{i}\n:PROPERTIES:\n:CONFIDENCE: 90\n:VERDICT: real\n:END:\n" for i in (1, 2, 3)))

    counts = findings_org.build(str(run), {})

    assert [p["id"] for p in findings_org.parse(run / "findings.org")] == ["r-01"]
    assert len(counts["malformed"]) == 2
    assert any("r-02" in m and "EFFORT" in m for m in counts["malformed"])


def test_build_rejects_duplicate_ids_across_surveys(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    for name in ("a", "b"):
        (run / "surveys" / f"{name}.org").write_text("* Findings\n" + _survey("r", 1))
    (run / "verification.org").write_text("#+TITLE: V\n")

    with pytest.raises(ValueError, match="r-01"):
        findings_org.build(str(run), {})
