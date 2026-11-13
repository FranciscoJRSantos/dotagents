"""Tests for skills/assess/rank.py: priority, overrides, caps, grouping."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "assess"))

import rank  # noqa: E402


def f(id, impact=3, interest=3, effort=3, repo="r", tags=(), **extra):
    return {
        "id": id,
        "repo": repo,
        "impact": impact,
        "interest": interest,
        "effort": effort,
        "tags": list(tags),
        **extra,
    }


def ids(items):
    return [x["id"] for x in items]


def test_priority_is_impact_times_interest_over_effort():
    assert rank.priority(f("a", impact=4, interest=3, effort=2)) == 6.0


def test_quick_wins_are_cheap_and_material_strategic_are_expensive_and_material():
    out = rank.rank([f("q", impact=4, effort=1), f("s", impact=4, effort=4), f("t", impact=1)])

    assert ids(out["quick_wins"]) == ["q"]
    assert ids(out["strategic"]) == ["s"]
    assert ids(out["track"]) == ["t"]


def test_security_phi_and_data_correctness_outrank_higher_priority():
    low_security = f("sec", impact=3, interest=1, effort=4, tags=["security"])
    high = f("high", impact=5, interest=5, effort=1)

    out = rank.rank([high, low_security])

    assert ids(out["top5"])[0] == "sec"


def test_each_override_tag_counts():
    for tag in ("security", "phi", "data-correctness"):
        out = rank.rank([f("plain", impact=5, interest=5, effort=1), f("x", tags=[tag])])
        assert ids(out["top5"])[0] == "x"


def test_cap_of_15_per_repo_overflows_to_track():
    findings = [f(f"a{i}", impact=5, effort=1, interest=5 - (i % 3)) for i in range(20)]

    out = rank.rank(findings)

    assert len(out["quick_wins"]) + len(out["strategic"]) == 15
    assert len(out["track"]) == 5
    assert set(ids(out["track"])).isdisjoint(ids(out["quick_wins"]))


def test_cap_is_per_repo():
    findings = [f(f"a{i}", impact=5, effort=1, repo="a") for i in range(10)]
    findings += [f(f"b{i}", impact=5, effort=1, repo="b") for i in range(10)]

    out = rank.rank(findings)

    assert len(out["quick_wins"]) == 20
    assert out["track"] == []


def test_top5_is_system_wide_in_priority_order():
    findings = [f(f"x{i}", impact=5, interest=i + 1, effort=1, repo=f"r{i}") for i in range(7)]

    out = rank.rank(findings)

    assert ids(out["top5"]) == ["x6", "x5", "x4", "x3", "x2"]


def test_accepted_risk_is_grouped_apart_and_never_in_top5():
    out = rank.rank([f("risk", impact=5, effort=1, accepted_risk=True), f("ok", impact=3)])

    assert ids(out["accepted"]) == ["risk"]
    assert ids(out["top5"]) == ["ok"]


def test_nothing_material_when_only_track_or_accepted():
    out = rank.rank([f("t", impact=1)])

    assert out["nothing_material"] is True
    assert out["top5"] == []


def test_nothing_material_false_when_something_is_ranked():
    assert rank.rank([f("q", impact=4, effort=1)])["nothing_material"] is False


def test_bucket_by_confidence_and_citation():
    cited = "=app/a.py:12= shows it"
    assert rank.bucket({"confidence": 80, "evidence": cited}) == "kept"
    assert rank.bucket({"confidence": 79, "evidence": cited}) == "open"
    assert rank.bucket({"confidence": 50, "evidence": cited}) == "open"
    assert rank.bucket({"confidence": 49, "evidence": cited}) == "dropped"
    assert rank.bucket({"confidence": 95, "evidence": "no citation here"}) == "dropped"


def test_bucket_intentional_code_goes_to_looks_fine():
    assert rank.bucket({"confidence": 90, "evidence": "=a.py:1=", "verdict": "intentional"}) == "fine"


def test_bucket_mismatch_verdict_drops_even_at_high_confidence():
    assert rank.bucket({"confidence": 90, "evidence": "=a.py:1=", "verdict": "mismatch"}) == "dropped"
