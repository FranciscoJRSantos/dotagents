"""Tests for skills/assess/hotspots.py: commits and authors per file in a window."""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent / "skills" / "assess"
sys.path.insert(0, str(HERE))

import hotspots  # noqa: E402


def _git(repo, *args, date=None, author="Ana"):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": f"{author.lower()}@example.com",
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": f"{author.lower()}@example.com",
    }
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env, capture_output=True)


def _commit(repo, files, author="Ana", date=None):
    for name in files:
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(p.read_text() + "x\n" if p.exists() else "x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "c", date=date, author=author)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def _recent():
    import datetime

    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=5)).isoformat()


def test_counts_commits_and_authors_sorted_by_commits(tmp_path):
    repo = _repo(tmp_path)
    d = _recent()
    _commit(repo, ["a.py", "b.py"], author="Ana", date=d)
    _commit(repo, ["a.py"], author="Bruno", date=d)
    _commit(repo, ["a.py"], author="Ana", date=d)

    result = hotspots.hotspots(repo)

    assert [h["path"] for h in result] == ["a.py", "b.py"]
    assert result[0] == {"path": "a.py", "commits": 3, "authors": 2}
    assert result[1] == {"path": "b.py", "commits": 1, "authors": 1}


def test_commits_outside_window_are_ignored(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, ["old.py"], date="2020-01-01T00:00:00+00:00")
    _commit(repo, ["new.py"], date=_recent())

    result = hotspots.hotspots(repo, months=6)

    assert [h["path"] for h in result] == ["new.py"]


def test_empty_repo_returns_empty_list(tmp_path):
    assert hotspots.hotspots(_repo(tmp_path)) == []


def test_cli_prints_json(tmp_path):
    repo = _repo(tmp_path)
    _commit(repo, ["a.py"], date=_recent())

    out = subprocess.run(
        [sys.executable, "-I", str(HERE / "hotspots.py"), str(repo)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert json.loads(out) == [{"path": "a.py", "commits": 1, "authors": 1}]


def test_not_a_repo_fails_loudly(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", str(HERE / "hotspots.py"), str(tmp_path / "nope")],
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert proc.stdout == ""
