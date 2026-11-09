"""Tests for the shared bin/ scripts deployed to ~/.agents/bin/.

Each script is driven through subprocess, the way skills call it. artifact-dir
runs inside a throwaway git repo in tmp_path so the branch name (and its ticket
key) is under test control.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "md2org"


def run(script, *args, cwd=None, stdin=None):
    return subprocess.run(
        [str(BIN / script), *map(str, args)],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
    )


# ── slug ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Org artifacts & per-work folders!", "org-artifacts-per-work-folders"),
        ("  --Hello,   World--  ", "hello-world"),
        ("PROJ-123 Fix the login redirect", "proj-123-fix-the-login-redirect"),
        ("Ünïcode café: déjà vu", "unicode-cafe-deja-vu"),
    ],
)
def test_slug_normalises(text, expected):
    result = run("slug", text)
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected + "\n"


def test_slug_cuts_long_titles_on_a_word_boundary():
    text = "Migrate the agent artifacts from markdown to org and group them per work"
    out = run("slug", text).stdout.strip()
    assert len(out) <= 40
    assert out == "migrate-the-agent-artifacts-from"
    assert text.lower().replace(" ", "-").startswith(out)


def test_slug_hard_cuts_a_single_overlong_word():
    out = run("slug", "a" * 60).stdout.strip()
    assert out == "a" * 40


def test_slug_rejects_input_with_no_usable_characters():
    result = run("slug", "!!! ???")
    assert result.returncode != 0
    assert result.stdout == ""


# ── org-check ──────────────────────────────────────────────────────────

CLEAN_ORG = """#+TITLE: Clean
#+CREATED: 2026-11-06T00:00:00Z

* Heading
Some *bold* text, =code= and [[https://example.com][a link]].

#+begin_src bash
# a shell comment, not a heading
echo `date` **not bold** [x](https://example.com)
```
#+end_src

#+BEGIN_SRC python
# uppercase block markers are skipped too
x = "`tick`"
#+END_SRC
"""


def test_org_check_passes_a_clean_file(tmp_path):
    f = tmp_path / "clean.org"
    f.write_text(CLEAN_ORG)
    result = run("org-check", f)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "leftover",
    [
        "```bash",
        "# A markdown heading",
        "### Deeper heading",
        "Some **bold** text",
        "See [docs](https://example.com)",
        "Run `make lint` first",
    ],
)
def test_org_check_flags_markdown_leftovers_outside_blocks(tmp_path, leftover):
    f = tmp_path / "bad.org"
    f.write_text(CLEAN_ORG + "\n" + leftover + "\n")
    result = run("org-check", f)
    assert result.returncode == 1
    line_no = len(CLEAN_ORG.splitlines()) + 2
    assert result.stdout.startswith(f"{f}:{line_no}: ")
    assert leftover in result.stdout


def test_org_check_ignores_markdown_quoted_in_verbatim_spans(tmp_path):
    f = tmp_path / "quoted.org"
    f.write_text(CLEAN_ORG + "Leftovers are =**bold**=, ~`code`~ and =](http= links.\n")
    result = run("org-check", f)
    assert result.returncode == 0, result.stdout


def test_org_check_still_flags_leftovers_next_to_verbatim_spans(tmp_path):
    f = tmp_path / "mixed.org"
    f.write_text(CLEAN_ORG + "Run =make= and **then** =lint=.\n")
    assert run("org-check", f).returncode == 1


def test_org_check_does_not_treat_stray_equals_as_a_verbatim_span(tmp_path):
    f = tmp_path / "stray.org"
    f.write_text(CLEAN_ORG + "invoice a=3: **bold** x=8 total\n")
    assert run("org-check", f).returncode == 1


def test_org_check_flags_an_unclosed_block(tmp_path):
    f = tmp_path / "unclosed.org"
    f.write_text("* Heading\n#+begin_src sh\necho hi\nRun `x` here\n")
    result = run("org-check", f)
    assert result.returncode == 1
    assert f"{f}:2: " in result.stdout
    assert "unclosed" in result.stdout


def test_org_check_checks_every_file_and_resets_blocks_per_file(tmp_path):
    first = tmp_path / "first.org"
    first.write_text("#+begin_src sh\n#+end_src\n")
    second = tmp_path / "second.org"
    second.write_text("Run `x` here\n")
    result = run("org-check", first, second)
    assert result.returncode == 1
    assert result.stdout.startswith(f"{second}:1: ")


def test_org_check_errors_on_a_missing_file(tmp_path):
    result = run("org-check", tmp_path / "missing.org")
    assert result.returncode == 2


# ── md2org ─────────────────────────────────────────────────────────────

MD = """# My title

Intro with **bold**, `code` and a [link](https://example.com).

## Section

```bash
# comment
echo hi
```

| A | B |
|---|---|
| 1 | 2 |
"""


def test_md2org_converts_and_prepends_keywords(tmp_path):
    src = tmp_path / "in.md"
    src.write_text(MD)
    out = tmp_path / "out.org"
    result = run("md2org", src, out, "TICKET=PROJ-1", "STATUS=clean")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = out.read_text().splitlines()
    assert lines[0] == "#+TITLE: My title"
    assert lines[1].startswith("#+CREATED: ")
    assert lines[1] != "#+CREATED: "
    assert lines[2:4] == ["#+TICKET: PROJ-1", "#+STATUS: clean"]
    body = "\n".join(lines)
    assert not re.search(r"^\s*:CUSTOM_ID:", body, re.M)
    assert "*bold*" in body and "=code=" in body
    assert "#+begin_src sh" in body  # pandoc maps bash to sh
    assert "** Section" in body


def test_md2org_explicit_title_and_created_win(tmp_path):
    src = tmp_path / "in.md"
    src.write_text(MD)
    out = tmp_path / "out.org"
    result = run("md2org", src, out, "TITLE=Given", "CREATED=2026-01-01T00:00:00Z")
    assert result.returncode == 0, result.stderr
    lines = out.read_text().splitlines()
    assert lines[:2] == ["#+TITLE: Given", "#+CREATED: 2026-01-01T00:00:00Z"]
    assert sum(1 for line in lines if line.startswith("#+TITLE:")) == 1


def test_md2org_omits_empty_keywords(tmp_path):
    src = tmp_path / "in.md"
    src.write_text(MD)
    out = tmp_path / "out.org"
    assert run("md2org", src, out, "TICKET=").returncode == 0
    assert "#+TICKET" not in out.read_text()


def test_md2org_title_falls_back_to_file_name(tmp_path):
    src = tmp_path / "notes.md"
    src.write_text("Just a paragraph.\n")
    out = tmp_path / "out.org"
    assert run("md2org", src, out).returncode == 0
    assert out.read_text().splitlines()[0] == "#+TITLE: notes"


def test_md2org_stdin_title_falls_back_to_output_name(tmp_path):
    out = tmp_path / "decisions.org"
    assert run("md2org", "-", out, stdin="No heading here.\n").returncode == 0
    assert out.read_text().splitlines()[0] == "#+TITLE: decisions"


def test_md2org_reads_stdin(tmp_path):
    out = tmp_path / "out.org"
    result = run("md2org", "-", out, "TITLE=From stdin", stdin=MD)
    assert result.returncode == 0, result.stderr
    assert "** Section" in out.read_text()


def test_md2org_rejects_bad_keyword_arguments(tmp_path):
    src = tmp_path / "in.md"
    src.write_text(MD)
    for bad in ["ticket=x", "NOEQUALS"]:
        result = run("md2org", src, tmp_path / "out.org", bad)
        assert result.returncode == 2, bad


def test_md2org_fails_when_leftovers_survive(tmp_path):
    # Escaped backticks pass through pandoc verbatim, so a Markdown code span
    # survives conversion and must be caught by org-check.
    src = tmp_path / "in.md"
    src.write_text("Intro.\n\nRun \\`leaked\\` here.\n")
    out = tmp_path / "out.org"
    result = run("md2org", src, out)
    assert result.returncode == 1
    assert "`leaked`" in result.stdout


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.md")), ids=lambda p: p.name)
def test_md2org_converts_real_artifacts_clean(tmp_path, fixture):
    out = tmp_path / "out.org"
    result = run("md2org", fixture, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not re.search(r"^\s*:CUSTOM_ID:", out.read_text(), re.M)


# ── artifact-dir ───────────────────────────────────────────────────────


def git_repo(path, branch="main"):
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    return path


def work(repo, slug, where="artifacts", ticket=None):
    d = repo / ".agents" / where / slug
    d.mkdir(parents=True)
    header = f"#+TITLE: {slug}\n" + (f"#+TICKET: {ticket}\n" if ticket else "")
    (d / "decisions.org").write_text(header)
    return d


def test_artifact_dir_none_without_agents_dir(tmp_path):
    repo = git_repo(tmp_path)
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "NONE\n"


def test_artifact_dir_none_with_only_archived_work(tmp_path):
    repo = git_repo(tmp_path)
    work(repo, "old", where="archive")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "NONE\n"
    assert (repo / ".agents/archive/old").is_dir()


def test_artifact_dir_picks_the_only_active_folder(tmp_path):
    repo = git_repo(tmp_path)
    work(repo, "only-one")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 0
    assert result.stdout == "ARTIFACT_DIR=.agents/artifacts/only-one\n"


def test_artifact_dir_ambiguous_with_two_active_folders(tmp_path):
    repo = git_repo(tmp_path)
    work(repo, "beta")
    work(repo, "alpha")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "AMBIGUOUS: alpha beta\n"


def test_artifact_dir_explicit_slug_wins(tmp_path):
    repo = git_repo(tmp_path, branch="feat/PROJ-9-other")
    work(repo, "alpha")
    work(repo, "beta", ticket="PROJ-9")
    result = run("artifact-dir", "alpha", cwd=repo)
    assert result.returncode == 0
    assert result.stdout == "ARTIFACT_DIR=.agents/artifacts/alpha\n"


def test_artifact_dir_explicit_slug_not_found(tmp_path):
    repo = git_repo(tmp_path)
    work(repo, "alpha")
    result = run("artifact-dir", "typo", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "NOT FOUND: typo\n"


def test_artifact_dir_matches_branch_ticket_via_keyword(tmp_path):
    repo = git_repo(tmp_path, branch="feat/PROJ-42-login")
    work(repo, "alpha")
    work(repo, "login-redirect", ticket="PROJ-42")
    work(repo, "proj-4-decoy", ticket="PROJ-4")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 0
    assert result.stdout == "ARTIFACT_DIR=.agents/artifacts/login-redirect\n"


def test_artifact_dir_ticket_matching_two_active_folders_is_ambiguous(tmp_path):
    repo = git_repo(tmp_path, branch="feat/PROJ-42-login")
    work(repo, "login-b", ticket="PROJ-42")
    work(repo, "login-a", ticket="PROJ-42")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "AMBIGUOUS: login-a login-b\n"


def test_artifact_dir_ticket_prefers_the_active_folder_over_archived(tmp_path):
    repo = git_repo(tmp_path, branch="feat/PROJ-42-login")
    work(repo, "login-old", where="archive", ticket="PROJ-42")
    work(repo, "login-new", ticket="PROJ-42")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 0
    assert result.stdout == "ARTIFACT_DIR=.agents/artifacts/login-new\n"
    assert (repo / ".agents/archive/login-old").is_dir()


def test_artifact_dir_ticket_matching_two_archived_folders_is_ambiguous(tmp_path):
    repo = git_repo(tmp_path, branch="feat/PROJ-42-login")
    work(repo, "login", where="archive", ticket="PROJ-42")
    work(repo, "login-20261106", where="archive", ticket="PROJ-42")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "AMBIGUOUS: login login-20261106\n"


def test_artifact_dir_ticket_without_match_falls_back_to_only_folder(tmp_path):
    repo = git_repo(tmp_path, branch="feat/PROJ-7-x")
    work(repo, "only-one")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 0
    assert result.stdout == "ARTIFACT_DIR=.agents/artifacts/only-one\n"


def test_artifact_dir_reopens_archived_explicit_slug(tmp_path):
    repo = git_repo(tmp_path)
    work(repo, "shipped", where="archive")
    result = run("artifact-dir", "shipped", cwd=repo)
    assert result.returncode == 0
    assert (
        result.stdout == "REOPENED: shipped\nARTIFACT_DIR=.agents/artifacts/shipped\n"
    )
    assert (repo / ".agents/artifacts/shipped/decisions.org").is_file()
    assert not (repo / ".agents/archive/shipped").exists()


def test_artifact_dir_reopens_archived_ticket_match(tmp_path):
    repo = git_repo(tmp_path, branch="PROJ-5-fixups")
    work(repo, "other")
    work(repo, "proj-5-thing", where="archive", ticket="PROJ-5")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 0
    assert (
        result.stdout
        == "REOPENED: proj-5-thing\nARTIFACT_DIR=.agents/artifacts/proj-5-thing\n"
    )


def test_artifact_dir_warns_on_legacy_layout_without_moving(tmp_path):
    repo = git_repo(tmp_path)
    work(repo, "only-one")
    legacy = repo / ".agents/artifacts/main-plan.md"
    legacy.write_text("---\nartifact: plan\n---\n")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 0
    assert result.stdout == "ARTIFACT_DIR=.agents/artifacts/only-one\n"
    assert "LEGACY LAYOUT" in result.stderr
    assert legacy.is_file()


@pytest.mark.parametrize("legacy", ["handoffs/20260101-000000.md", "STATE.md"])
def test_artifact_dir_warns_on_legacy_handoffs_and_state(tmp_path, legacy):
    repo = git_repo(tmp_path)
    path = repo / ".agents" / legacy
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    assert "LEGACY LAYOUT" in run("artifact-dir", cwd=repo).stderr


def test_artifact_dir_new_layout_global_handoff_is_not_legacy(tmp_path):
    repo = git_repo(tmp_path)
    path = repo / ".agents/handoffs/20260101-000000.org"
    path.parent.mkdir(parents=True)
    path.write_text("x")
    (repo / ".agents/STATE.org").write_text("x")
    result = run("artifact-dir", cwd=repo)
    assert result.returncode == 1
    assert result.stdout == "NONE\n"
    assert result.stderr == ""


def test_scripts_are_executable():
    for name in ["artifact-dir", "md2org", "org-check", "slug"]:
        assert shutil.which(name, path=str(BIN)), name
