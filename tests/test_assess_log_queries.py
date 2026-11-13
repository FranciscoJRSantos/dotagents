"""Guards for skills/assess/log-queries.md: totals only, IDs structurally excluded.

The log check must never put a raw log line, payload or caller identity into an
artifact. These tests pin the PHI guard on the query templates themselves.
"""

import re
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "skills" / "assess" / "log-queries.md"


def _queries():
    text = DOC.read_text()
    return re.findall(r"```insights\n(.*?)```", text, re.DOTALL)


def test_templates_exist():
    assert len(_queries()) >= 3


def test_every_query_aggregates_with_stats_count():
    for q in _queries():
        assert re.search(r"^\| stats count\(\*\)", q, re.MULTILINE), q


def test_raw_message_is_only_ever_parsed_never_displayed():
    for q in _queries():
        for line in q.splitlines():
            if "@message" in line:
                assert line.lstrip("| ").startswith("parse @message"), line
        assert "display" not in q, q
        assert "@log" not in q, q


def test_no_query_returns_rows_without_aggregation():
    for q in _queries():
        assert "| limit" not in q or "stats" in q.split("| limit")[0], q


def test_queries_never_capture_ids_or_addresses():
    for q in _queries():
        assert "client" not in q.lower(), q  # no client ip / client port field
        assert not re.search(r"\(\?<(ip|user|patient|id|email)\w*>", q), q


def test_doc_states_the_guard():
    text = DOC.read_text().lower()
    assert "totals only" in text
    assert "never" in text and "raw" in text


def test_route_capture_cannot_take_digit_bearing_segments():
    route = re.search(r"\(\?<route>(.*?)\)\[\^ \]", DOC.read_text()).group(1)
    assert route == r"(\/(v\d+|[A-Za-z_-]+)){1,3}"
    # the only digit class allowed is the version prefix v<digits>
    assert route.count(r"\d") == 1


def test_doc_covers_status_polling_and_unlisted_routes():
    text = DOC.read_text()
    assert "Complete" in text and "<unlisted>" in text
    assert "GRAFANA_TOKEN" in text
