"""Tests for skills/reporting/phi_scan.py: stop a report that looks like patient data."""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "skills" / "reporting"
sys.path.insert(0, str(HERE))

import phi_scan  # noqa: E402

CLEAN = """\
# Tech assessment: AIH

Quick wins: split =app/routes.py:42= and add a timeout to =app/client.py:9=.
The queue ~billing-events~ has no dead-letter queue. See https://example.com/adr/4.
Release 2026.11 shipped on 2026-11-13; 3 of 13 repos are red.
"""


def kinds(text):
    return [h["kind"] for h in phi_scan.scan(text)]


def test_clean_report_has_no_hits():
    assert phi_scan.scan(CLEAN) == []


def test_mrn_hits():
    assert kinds("Patient MRN: 00123456 was affected") == ["mrn"]
    assert kinds("mrn 998877") == ["mrn"]
    assert kinds("MRN: A12345678") == ["mrn"]
    assert kinds("MRN: 12 345 678") == ["mrn"]
    assert kinds("MRN (1234567)") == ["mrn"]
    assert kinds("MRN. 1234567") == ["mrn"]
    assert kinds("the MRN field is mapped in the schema") == []


def test_ssn_hits():
    assert kinds("SSN 123-45-6789 in the fixture") == ["ssn"]


def test_dob_hits():
    assert kinds("DOB: 1980-02-14") == ["dob"]
    assert kinds("date of birth 02/14/1980") == ["dob"]


def test_email_hits():
    assert kinds("contact jane.doe@clinic.org for details") == ["email"]


def test_phone_hits():
    assert kinds("call (555) 123-4567 now") == ["phone"]
    assert kinds("call 555-123-4567 now") == ["phone"]
    assert kinds("ligue +351 912 345 678") == ["phone"]


def test_raw_log_line_hits():
    assert kinds("2026-11-13T10:22:31Z INFO request handled user=42") == ["log-line"]
    assert kinds("2026-11-13 10:22:31,123 ERROR boom") == ["log-line"]
    assert kinds('https 2026-11-13T10:22:31.123456Z app/lb/abc 10.0.0.1:5000 "GET https://x/y HTTP/1.1"') == ["log-line"]


def test_dates_and_version_numbers_are_not_flagged():
    assert phi_scan.scan("Released 2026-11-13, v1.2.3, build 20261113, port 5432.") == []


def test_hits_report_one_based_line_numbers_and_kinds():
    text = "ok line\nSSN 123-45-6789\nfine\ncontact a@b.co\n"

    hits = phi_scan.scan(text)

    assert [(h["line"], h["kind"]) for h in hits] == [(2, "ssn"), (4, "email")]


def test_hits_never_echo_the_matched_value():
    hits = phi_scan.scan("SSN 123-45-6789 and jane.doe@clinic.org")

    for h in hits:
        assert "123-45-6789" not in str(h) and "jane.doe" not in str(h)


def test_cli_exit_codes_and_output_is_masked(tmp_path):
    dirty = tmp_path / "dirty.md"
    dirty.write_text("line one\nSSN 123-45-6789\n")
    clean = tmp_path / "clean.md"
    clean.write_text(CLEAN)

    run = lambda p: subprocess.run(  # noqa: E731
        [sys.executable, "-I", str(HERE / "phi_scan.py"), str(p)], capture_output=True, text=True)

    bad = run(dirty)
    assert bad.returncode == 1
    assert "line 2: ssn" in bad.stdout
    assert "123-45-6789" not in bad.stdout + bad.stderr
    ok = run(clean)
    assert ok.returncode == 0
    assert "123" not in ok.stdout


def test_cli_missing_file_is_an_error(tmp_path):
    proc = subprocess.run([sys.executable, "-I", str(HERE / "phi_scan.py"), str(tmp_path / "no.md")],
                          capture_output=True, text=True)

    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_cli_usage_error_exits_2_not_1():
    proc = subprocess.run([sys.executable, "-I", str(HERE / "phi_scan.py")], capture_output=True, text=True)

    assert proc.returncode == 2
