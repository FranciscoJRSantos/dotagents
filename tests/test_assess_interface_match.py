"""Tests for skills/assess/interface_match.py: two-way match of consumed vs exposed."""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "skills" / "assess"
sys.path.insert(0, str(HERE))

import interface_match as im  # noqa: E402


def e(name, cite="a.py:1", target=None):
    return {"name": name, "cite": cite, "target": target}


def sheet(exposes=(), consumes=(), config=()):
    return {"exposes": list(exposes), "consumes": list(consumes), "config": list(config)}


def names(items):
    return sorted((i["repo"], i["name"]) for i in items)


def test_matched_pair_across_repos():
    sheets = {
        "api": sheet(exposes=[e("GET /v1/patients")]),
        "web": sheet(consumes=[e("GET /v1/patients")]),
    }

    out = im.match(sheets, tf_decls=set())

    assert out["unmatched_consumers"] == [] and out["unmatched_producers"] == []
    assert out["matched"] == [{"name": "GET /v1/patients", "producer": "api", "consumers": ["web"]}]


def test_unmatched_consumer():
    sheets = {"web": sheet(consumes=[e("GET /v1/ghost", "w.py:9")])}

    out = im.match(sheets, tf_decls=set())

    assert names(out["unmatched_consumers"]) == [("web", "GET /v1/ghost")]
    assert out["unmatched_consumers"][0]["cite"] == "w.py:9"


def test_unmatched_producer():
    sheets = {"api": sheet(exposes=[e("queue:orphan-events")])}

    out = im.match(sheets, tf_decls=set())

    assert names(out["unmatched_producers"]) == [("api", "queue:orphan-events")]


def test_own_exposure_does_not_match_own_consumption():
    sheets = {"api": sheet(exposes=[e("GET /x")], consumes=[e("GET /x")])}

    out = im.match(sheets, tf_decls=set())

    assert names(out["unmatched_consumers"]) == [("api", "GET /x")]
    assert names(out["unmatched_producers"]) == [("api", "GET /x")]


def test_terraform_only_match():
    sheets = {"worker": sheet(consumes=[e("queue:billing-events")])}

    out = im.match(sheets, tf_decls={"queue:billing-events"})

    assert out["unmatched_consumers"] == []
    assert out["matched"] == [{"name": "queue:billing-events", "producer": "terraform", "consumers": ["worker"]}]


def test_openapi_wins_over_survey_for_http_routes():
    sheets = {
        "api": sheet(exposes=[e("GET /v1/a"), e("GET /v1/b")]),
        "web": sheet(consumes=[e("GET /v1/a"), e("GET /v1/b")]),
    }

    out = im.match(sheets, tf_decls=set(), openapi={"GET /v1/a"})

    assert names(out["unmatched_consumers"]) == [("web", "GET /v1/b")]
    assert [m["name"] for m in out["matched"]] == ["GET /v1/a"]
    assert out["matched"][0]["producer"] == "openapi"
    # the surveyed-but-undocumented route is a producer the spec does not declare
    assert names(out["unmatched_producers"]) == [("api", "GET /v1/b")]


def test_openapi_covers_a_route_no_survey_exposed():
    sheets = {"web": sheet(consumes=[e("POST /v1/export")])}

    out = im.match(sheets, tf_decls=set(), openapi={"POST /v1/export"})

    assert out["unmatched_consumers"] == []


def test_normalisation_ignores_case_trailing_slash_and_params():
    sheets = {
        "api": sheet(exposes=[e("get /v1/patients/{id}/")]),
        "web": sheet(consumes=[e("GET /v1/patients/:id")]),
    }

    out = im.match(sheets, tf_decls=set())

    assert out["unmatched_consumers"] == []


def test_service_level_consumer_matches_repo_that_exposes_something():
    sheets = {
        "api": sheet(exposes=[e("GET /v1/x")]),
        "web": sheet(consumes=[e("PATIENT_API_URL", target="api")]),
    }

    out = im.match(sheets, tf_decls=set())

    assert out["unmatched_consumers"] == []
    assert out["matched"][0]["producer"] == "api"


def test_parse_sheet_reads_the_org_interface_sheet(tmp_path):
    survey = tmp_path / "s.org"
    survey.write_text(
        "* Findings\n\n* Interface sheet\n** Exposes\n"
        "- =GET /v1/patients= (HTTP) — =app/routes.py:42=\n"
        "** Consumes\n"
        "- =PATIENT_API_URL= → patient-service (HTTP) — =app/client.py:9=\n"
        "- =queue:billing-events= (SQS consumer) — =app/worker.py:31=\n"
        "** Config\n- =DATABASE_URL= (env, required) — =config/settings.py:5=\n"
    )

    parsed = im.parse_sheet(survey)

    assert parsed["exposes"] == [{"name": "GET /v1/patients", "cite": "app/routes.py:42", "target": None}]
    assert parsed["consumes"][0] == {"name": "PATIENT_API_URL", "cite": "app/client.py:9", "target": "patient-service"}
    assert parsed["consumes"][1]["name"] == "queue:billing-events"
    assert parsed["config"][0]["name"] == "DATABASE_URL"


def test_parse_terraform_declarations():
    tf = (
        'resource "aws_sqs_queue" "billing" {\n  name = "billing-events"\n}\n'
        'resource "aws_s3_bucket" "models" {\n  bucket = "aih-models"\n}\n'
        'resource "aws_sns_topic" "alerts" {\n  name = "alerts"\n}\n'
        'resource "aws_sqs_queue" "unnamed" {\n}\n'
        'resource "aws_dynamodb_table" "users" {\n  name = "users"\n}\n'
    )

    assert im.parse_terraform(tf) == {
        "queue:billing-events", "s3://aih-models", "topic:alerts", "queue:unnamed", "table:users",
    }


def test_render_lists_unmatched_with_citations():
    out = im.match({"web": sheet(consumes=[e("GET /v1/ghost", "w.py:9")])}, tf_decls=set())

    text = im.render(out)

    assert "* Interface match" in text
    assert "=GET /v1/ghost=" in text and "=w.py:9=" in text
    assert "web" in text


def test_cli_prints_json(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    (run / "surveys" / "web.org").write_text(
        "* Interface sheet\n** Exposes\n** Consumes\n- =GET /v1/ghost= (HTTP) — =w.py:9=\n** Config\n")

    proc = subprocess.run(
        [sys.executable, "-I", str(HERE / "interface_match.py"), str(run)],
        capture_output=True, text=True, check=True,
    )

    assert json.loads(proc.stdout)["unmatched_consumers"][0]["repo"] == "web"


def test_empty_openapi_falls_back_to_surveys(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    (run / "surveys" / "api.org").write_text("* Interface sheet\n** Exposes\n- =GET /v1/x= (HTTP) — =a.py:1=\n** Consumes\n** Config\n")
    (run / "surveys" / "web.org").write_text("* Interface sheet\n** Exposes\n** Consumes\n- =GET /v1/x= (HTTP) — =w.py:1=\n** Config\n")
    empty = tmp_path / "keys.txt"
    empty.write_text("")

    proc = subprocess.run([sys.executable, "-I", str(HERE / "interface_match.py"), str(run), "--openapi", str(empty)],
                          capture_output=True, text=True, check=True)

    assert json.loads(proc.stdout)["unmatched_consumers"] == []


def test_separators_are_equivalent_for_non_http_names():
    sheets = {"w": sheet(consumes=[e("queue:billing_events")])}

    assert im.match(sheets, tf_decls={"queue:billing-events"})["unmatched_consumers"] == []


def test_cli_missing_tf_file_fails_without_traceback(tmp_path):
    run = tmp_path / "run"
    (run / "surveys").mkdir(parents=True)
    (run / "surveys" / "a.org").write_text("* Interface sheet\n** Exposes\n** Consumes\n** Config\n")

    proc = subprocess.run([sys.executable, "-I", str(HERE / "interface_match.py"), str(run), "--tf", str(tmp_path / "no.tf")],
                          capture_output=True, text=True)

    assert proc.returncode != 0
    assert "not found" in proc.stderr and "Traceback" not in proc.stderr
