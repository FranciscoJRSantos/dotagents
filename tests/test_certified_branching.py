"""Tests for per-slice branch creation in certified projects.

Verifies that @build creates per-slice branches with correct parentage
based on the dependency graph from the kanban board.
"""

import subprocess
import tempfile
from pathlib import Path
import yaml
import re


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_git(args: list[str], cwd: Path) -> tuple[int, str]:
    """Run a git command and return (exitcode, stdout)."""
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.returncode, result.stdout.strip()


def _create_test_repo() -> Path:
    """Create a temporary git repo with initial commit."""
    tmpdir = Path(tempfile.mkdtemp())

    # Initialize git repo
    _run_git(["init"], tmpdir)
    _run_git(["config", "user.email", "test@example.com"], tmpdir)
    _run_git(["config", "user.name", "Test User"], tmpdir)

    # Create epic branch
    _run_git(["checkout", "-b", "epic-branch"], tmpdir)

    # Initial commit
    (tmpdir / "README.md").write_text("# Test\n")
    _run_git(["add", "README.md"], tmpdir)
    _run_git(["commit", "-m", "Initial commit"], tmpdir)

    return tmpdir


def _create_kanban_board(tmpdir: Path, slices: list[dict]):
    """Create a board.org artifact in Org format."""
    artifacts_dir = tmpdir / ".agents" / "artifacts" / "test-work"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Build board.org with Org TODO keywords and property drawers
    lines = [
        "#+TITLE: Board: Test",
        "#+CREATED: 2026-01-01T00:00:00Z",
        "#+TODO: TODO DOING | DONE SKIPPED",
        "",
    ]

    for s in slices:
        sid = s["id"]
        title = s["title"]
        blocked_by = s.get("blocked_by", [])
        lines.extend(
            [
                f"* TODO Slice {sid}: {title}",
                ":PROPERTIES:",
                f":SLICE: {sid}",
                ":MODE: afk",
                f":BLOCKS:",
                f":BLOCKED_BY: {' '.join(map(str, blocked_by))}",
                ":COMMIT:",
                ":END:",
                f"Description for slice {sid}.",
                "",
                "** Module interfaces",
                f"- =file{sid}.txt= — Interface for slice {sid}.",
                "",
            ]
        )

    (artifacts_dir / "board.org").write_text("\n".join(lines))


def _create_project_yaml(tmpdir: Path, certified: bool):
    """Create a project.yaml with certified flag."""
    agents_dir = tmpdir / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    content = f"certified: {'true' if certified else 'false'}\n"
    (agents_dir / "project.yaml").write_text(content)


def _extract_branch_creation_snippet() -> str:
    """Extract the Step 2a branch creation snippet from build/SKILL.md."""
    skill_file = REPO_ROOT / "skills" / "build" / "SKILL.md"
    text = skill_file.read_text()

    # Find the Step 2a section
    match = re.search(
        r"### 2a: Create Slice Branch.*?```bash\n(.*?)```",
        text,
        re.DOTALL,
    )
    assert match, "Step 2a snippet not found in build/SKILL.md"
    snippet = match.group(1)

    # Strip HTML comment markers (they're for documentation, not bash execution)
    snippet = re.sub(r"<!--.*?-->", "", snippet, flags=re.DOTALL)

    return snippet


def test_certified_project_creates_slice_branch_from_epic():
    """Certified project: slice with no deps branches from epic."""
    tmpdir = _create_test_repo()

    slices = [{"id": 1, "title": "First", "blocked_by": []}]
    _create_kanban_board(tmpdir, slices)
    _create_project_yaml(tmpdir, certified=True)

    # Extract and run the snippet
    snippet = _extract_branch_creation_snippet()
    env_vars = f"SLICE_ID=1 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"

    result = subprocess.run(
        ["bash", "-c", f"{env_vars}\n{snippet}"],
        capture_output=True,
        text=True,
        cwd=tmpdir,
    )

    assert result.returncode == 0, f"Snippet failed: {result.stderr}"

    # Verify branch was created
    rc, branches = _run_git(["branch", "--list", "epic-branch-s1"], tmpdir)
    assert "epic-branch-s1" in branches

    # Verify we're on the new branch
    rc, current = _run_git(["branch", "--show-current"], tmpdir)
    assert current == "epic-branch-s1"


def test_certified_project_slice_with_dependency():
    """Certified project: slice with dependency branches from parent."""
    tmpdir = _create_test_repo()

    slices = [
        {"id": 1, "title": "First", "blocked_by": []},
        {"id": 2, "title": "Second", "blocked_by": [1]},
    ]
    _create_kanban_board(tmpdir, slices)
    _create_project_yaml(tmpdir, certified=True)

    # Create slice 1 branch
    snippet = _extract_branch_creation_snippet()
    env_vars = f"SLICE_ID=1 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"
    subprocess.run(["bash", "-c", f"{env_vars}\n{snippet}"], cwd=tmpdir, check=True)

    # Make a commit on slice 1
    (tmpdir / "file1.txt").write_text("slice 1\n")
    _run_git(["add", "file1.txt"], tmpdir)
    _run_git(["commit", "-m", "Slice 1"], tmpdir)

    # Return to epic
    _run_git(["checkout", "epic-branch"], tmpdir)

    # Create slice 2 branch
    env_vars = f"SLICE_ID=2 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"
    result = subprocess.run(
        ["bash", "-c", f"{env_vars}\n{snippet}"],
        capture_output=True,
        text=True,
        cwd=tmpdir,
    )

    assert result.returncode == 0, f"Snippet failed: {result.stderr}"

    # Verify slice 2 branch exists and contains slice 1's commit
    rc, branches = _run_git(["branch", "--list", "epic-branch-s2"], tmpdir)
    assert "epic-branch-s2" in branches

    # Verify slice 2 has slice 1's changes (file1.txt should exist)
    assert (tmpdir / "file1.txt").exists()


def test_non_certified_project_no_branch_creation():
    """Non-certified project: no slice branches created."""
    tmpdir = _create_test_repo()
    _create_project_yaml(tmpdir, certified=False)

    # Extract and run the snippet
    snippet = _extract_branch_creation_snippet()
    env_vars = f"SLICE_ID=1 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"

    result = subprocess.run(
        ["bash", "-c", f"{env_vars}\n{snippet}"],
        capture_output=True,
        text=True,
        cwd=tmpdir,
    )

    assert result.returncode == 0

    # Verify no slice branches created
    rc, branches = _run_git(["branch", "--list", "epic-branch-s*"], tmpdir)
    assert "epic-branch-s" not in branches

    # Verify still on epic branch
    rc, current = _run_git(["branch", "--show-current"], tmpdir)
    assert current == "epic-branch"


def test_certified_project_rejects_multiple_dependencies():
    """Certified project: slice with multiple dependencies is rejected."""
    tmpdir = _create_test_repo()

    slices = [
        {"id": 1, "title": "A", "blocked_by": []},
        {"id": 2, "title": "B", "blocked_by": []},
        {"id": 3, "title": "C", "blocked_by": [1, 2]},
    ]
    _create_kanban_board(tmpdir, slices)
    _create_project_yaml(tmpdir, certified=True)

    # Try to create slice 3 (has 2 dependencies)
    snippet = _extract_branch_creation_snippet()
    env_vars = f"SLICE_ID=3 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"

    result = subprocess.run(
        ["bash", "-c", f"{env_vars}\n{snippet}"],
        capture_output=True,
        text=True,
        cwd=tmpdir,
    )

    # Should fail with error
    assert result.returncode != 0
    assert (
        "multiple dependencies" in result.stdout
        or "linear dependency chains" in result.stdout
    )


def test_resume_after_clear():
    """Resume after /clear: epic branch derived correctly from slice branch."""
    tmpdir = _create_test_repo()

    slices = [
        {"id": 1, "title": "First", "blocked_by": []},
        {"id": 2, "title": "Second", "blocked_by": []},
    ]
    _create_kanban_board(tmpdir, slices)
    _create_project_yaml(tmpdir, certified=True)

    # Create slice 1 branch
    snippet = _extract_branch_creation_snippet()
    env_vars = f"SLICE_ID=1 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"
    subprocess.run(["bash", "-c", f"{env_vars}\n{snippet}"], cwd=tmpdir, check=True)

    # Simulate /clear: we're still on epic-branch-s1
    rc, current = _run_git(["branch", "--show-current"], tmpdir)
    assert current == "epic-branch-s1"

    # Now create slice 2 (no deps) - should derive epic from current branch
    env_vars = f"SLICE_ID=2 DIR={tmpdir / '.agents' / 'artifacts' / 'test-work'}"
    result = subprocess.run(
        ["bash", "-c", f"{env_vars}\n{snippet}"],
        capture_output=True,
        text=True,
        cwd=tmpdir,
    )

    # This should succeed — the snippet derives the epic branch by stripping -s1
    # and creates epic-branch-s2 from epic-branch (not epic-branch-s1-s2)
    assert result.returncode == 0, (
        f"Snippet should succeed when resuming from a slice branch: {result.stderr}"
    )
    rc, branches = _run_git(["branch", "--list", "epic-branch-s2"], tmpdir)
    # Should create epic-branch-s2 from epic-branch (not epic-branch-s1-s2)
    assert "epic-branch-s2" in branches
    assert "epic-branch-s1-s2" not in branches


# ── @ship certified MR loop: Org board slice metadata ──────────────────


def _extract_org_slice_emitter() -> str:
    """Extract the Org slice-record emitter awk from ship/SKILL.md's certified loop."""
    skill_file = REPO_ROOT / "skills" / "ship" / "SKILL.md"
    text = skill_file.read_text()

    match = re.search(r"done < <\(awk '\n(.*?)\n    ' \"\$BOARD_FILE\"\)", text, re.DOTALL)
    assert match, "org slice emitter not found in ship/SKILL.md"
    return match.group(1)


def _run_slice_emitter(board_org: Path) -> str:
    """Run the emitter against a board.org; return stdout (tab-separated records)."""
    emitter = _extract_org_slice_emitter()
    result = subprocess.run(
        ["bash", "-c", "awk '" + emitter + "' \"$1\"", "awk-prog", str(board_org)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_slice_emitter_reads_ids_from_slice_not_position():
    """The certified MR loop drives from :SLICE:, so renumbered boards stay correct."""
    tmpdir = Path(tempfile.mkdtemp())
    board = tmpdir / "board.org"
    board.write_text(
        "#+TITLE: Board: Test\n"
        "#+CREATED: 2026-01-01T00:00:00Z\n"
        "#+TODO: TODO DOING | DONE SKIPPED\n"
        "\n"
        "* TODO Slice 1: Alpha\n"
        ":PROPERTIES:\n"
        ":SLICE: 1\n"
        ":MODE: hitl\n"
        ":BLOCKS:\n"
        ":BLOCKED_BY:\n"
        ":COMMIT:\n"
        ":END:\n"
        "alpha desc\n"
        "\n"
        "* TODO Slice 2: Beta\n"
        ":PROPERTIES:\n"
        ":SLICE: 2\n"
        ":MODE: afk\n"
        ":BLOCKS:\n"
        ":BLOCKED_BY: 1\n"
        ":COMMIT:\n"
        ":END:\n"
        "beta desc\n"
        "\n"
        "* TODO Slice 7: Gamma\n"
        "# a numbering gap: the old positional loop found nothing here\n"
        ":PROPERTIES:\n"
        ":SLICE: 7\n"
        ":MODE: afk\n"
        ":BLOCKS:\n"
        ":BLOCKED_BY: 2\n"
        ":COMMIT:\n"
        ":END:\n"
        "gamma desc\n"
        "\n"
        "* Notes\n"
        ":PROPERTIES:\n"
        ":DECOY: must not leak into any record\n"
        ":END:\n"
    )

    out = _run_slice_emitter(board)
    lines = out.splitlines()
    # Ids come from :SLICE: (including the gap), titles from the headings,
    # blocked_by from the drawers, non-slice headings close a record.
    assert lines == [
        "1\tAlpha\thitl\t",
        "2\tBeta\tafk\t1",
        "7\tGamma\tafk\t2",
    ], lines


def test_slice_emitter_defaults_mode_to_afk():
    """A slice without :MODE: is treated as afk, like @arch's default."""
    tmpdir = Path(tempfile.mkdtemp())
    board = tmpdir / "board.org"
    board.write_text(
        "#+TITLE: Board: Test\n"
        "#+CREATED: 2026-01-01T00:00:00Z\n"
        "\n"
        "* DOING Slice 3: Bare slice\n"
        ":PROPERTIES:\n"
        ":SLICE: 3\n"
        ":BLOCKS:\n"
        ":BLOCKED_BY:\n"
        ":COMMIT: abc1234\n"
        ":END:\n"
    )

    out = _run_slice_emitter(board)
    assert out == "3\tBare slice\tafk\t\n"
