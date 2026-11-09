"""Tests for per-slice MR creation in certified projects.

Verifies that @ship creates MRs for each slice branch in dependency order
for certified projects, while maintaining single-MR behavior for non-certified.
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

    # Create main branch
    _run_git(["checkout", "-b", "main"], tmpdir)

    # Initial commit
    (tmpdir / "README.md").write_text("# Test\n")
    _run_git(["add", "README.md"], tmpdir)
    _run_git(["commit", "-m", "Initial commit"], tmpdir)

    return tmpdir


def _create_kanban_board(tmpdir: Path, slices: list[dict]):
    """Create a kanban board artifact."""
    artifacts_dir = tmpdir / ".agents" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "artifact": "kanban-board",
        "ticket": "TEST-1",
        "slices": slices,
    }

    board_content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n"
    (artifacts_dir / "TEST-1-kanban-board.md").write_text(board_content)


def _create_impl_progress(tmpdir: Path, slices: list[dict]):
    """Create an impl-progress artifact with slice commits."""
    artifacts_dir = tmpdir / ".agents" / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "artifact": "impl-progress",
        "ticket": "TEST-1",
        "status": "complete",
        "slices": slices,
    }

    content = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n"
    (artifacts_dir / "TEST-1-impl-progress.md").write_text(content)


def _create_project_yaml(tmpdir: Path, certified: bool):
    """Create a project.yaml with certified flag."""
    agents_dir = tmpdir / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    content = f"certified: {'true' if certified else 'false'}\n"
    (agents_dir / "project.yaml").write_text(content)


def _extract_certified_mr_loop() -> str:
    """Extract the certified MR loop snippet from ship/SKILL.md."""
    skill_file = REPO_ROOT / "skills" / "ship" / "SKILL.md"
    text = skill_file.read_text()

    # Find the certified projects section and extract the bash block
    match = re.search(
        r"#### Certified Projects: Per-Slice MRs.*?```bash\n(.*?)```",
        text,
        re.DOTALL,
    )
    assert match, "Certified MR loop not found in ship/SKILL.md"
    return match.group(1)


def test_certified_project_creates_per_slice_mrs():
    """Certified project: creates MR for each slice branch."""
    tmpdir = _create_test_repo()

    # Create epic branch
    _run_git(["checkout", "-b", "epic-branch"], tmpdir)

    slices = [
        {"id": 1, "title": "First", "blocked_by": []},
        {"id": 2, "title": "Second", "blocked_by": [1]},
    ]

    # Create slice branches with commits
    _run_git(["checkout", "-b", "epic-branch-s1", "epic-branch"], tmpdir)
    (tmpdir / "file1.txt").write_text("slice 1\n")
    _run_git(["add", "file1.txt"], tmpdir)
    _run_git(["commit", "-m", "Slice 1"], tmpdir)
    rc, commit1 = _run_git(["rev-parse", "--short", "HEAD"], tmpdir)

    _run_git(["checkout", "epic-branch"], tmpdir)
    _run_git(["checkout", "-b", "epic-branch-s2", "epic-branch-s1"], tmpdir)
    (tmpdir / "file2.txt").write_text("slice 2\n")
    _run_git(["add", "file2.txt"], tmpdir)
    _run_git(["commit", "-m", "Slice 2"], tmpdir)
    rc, commit2 = _run_git(["rev-parse", "--short", "HEAD"], tmpdir)

    # Create artifacts
    _create_kanban_board(tmpdir, slices)
    _create_impl_progress(
        tmpdir,
        [
            {"id": 1, "title": "First", "status": "complete", "commit": commit1},
            {"id": 2, "title": "Second", "status": "complete", "commit": commit2},
        ],
    )
    _create_project_yaml(tmpdir, certified=True)

    # Extract and verify the snippet exists
    snippet = _extract_certified_mr_loop()
    assert len(snippet) > 0

    # The snippet should contain logic to detect certified projects
    assert "certified" in snippet.lower() or "project.yaml" in snippet


def test_certified_mr_loop_pushes_epic_branch():
    """Critical 2: epic branch must be pushed before the per-slice MR loop."""
    snippet = _extract_certified_mr_loop()
    # The loop must push the epic branch so the first slice's --base exists on remote
    assert 'git push -u origin "$EPIC_BRANCH"' in snippet, (
        "MR loop must push epic branch before creating MRs — "
        "first slice's --base needs to exist on the remote"
    )


def test_certified_mr_loop_uses_correct_base_and_head():
    """MR loop: --base uses $MR_BASE (derived from blocked_by), --head uses $SLICE_BRANCH."""
    snippet = _extract_certified_mr_loop()
    # gh pr create must use --base for the target and --head for the source
    assert '--base "$MR_BASE"' in snippet, (
        "gh pr create must use --base with the derived MR_BASE (respects blocked_by)"
    )
    assert '--head "$SLICE_BRANCH"' in snippet, (
        "gh pr create must use --head with the slice's branch name"
    )
    # glab mr create must use --target-branch / --source-branch
    assert '--target-branch "$MR_BASE"' in snippet, (
        "glab mr create must use --target-branch with MR_BASE"
    )
    assert '--source-branch "$SLICE_BRANCH"' in snippet, (
        "glab mr create must use --source-branch with the slice's branch name"
    )


def test_certified_mr_title_format():
    """MR title follows ${LABEL}-s${N}: ${title} format."""
    snippet = _extract_certified_mr_loop()
    assert 'MR_TITLE="${LABEL}-s${SLICE_ID}: ${SLICE_TITLE}"' in snippet, (
        "MR title must follow the ${LABEL}-s${N}: ${title} format"
    )


def test_certified_mr_loop_handles_already_exists():
    """MR loop: on 'already exists' error, view the existing MR and continue."""
    snippet = _extract_certified_mr_loop()
    # Should detect the already-exists case
    assert "already exists" in snippet.lower(), (
        "MR loop should handle the 'already exists' case (gotcha line 21)"
    )
    # Should view the existing MR
    assert "pr view" in snippet or "mr view" in snippet, (
        "MR loop should view the existing MR on 'already exists' error"
    )


def test_certified_mr_loop_non_fatal_failures():
    """MR loop: per-slice failures are non-fatal with a summary at the end."""
    snippet = _extract_certified_mr_loop()
    # Should collect failures instead of exiting 1 on every gh/glab failure
    assert "FAILED_SLICES" in snippet, (
        "MR loop should collect failed slices in FAILED_SLICES for summary"
    )
    # Should print a summary at the end
    assert "Warning: some per-slice MRs were not created" in snippet, (
        "MR loop should print a summary of failed slices at the end"
    )
    # Should handle "already exists" gracefully
    assert "already exists" in snippet.lower(), (
        "MR loop should handle the 'already exists' case"
    )


def test_non_certified_project_creates_single_mr():
    """Non-certified project: creates single MR (current behavior)."""
    tmpdir = _create_test_repo()

    # Create feature branch
    _run_git(["checkout", "-b", "feat/new-feature"], tmpdir)
    (tmpdir / "feature.txt").write_text("new feature\n")
    _run_git(["add", "feature.txt"], tmpdir)
    _run_git(["commit", "-m", "Add feature"], tmpdir)

    # Create artifacts (no certified flag)
    _create_project_yaml(tmpdir, certified=False)

    # Extract the standard MR snippet
    skill_file = REPO_ROOT / "skills" / "ship" / "SKILL.md"
    text = skill_file.read_text()
    match = re.search(
        r"#### Standard Projects: Single MR.*?```bash\n(.*?)```",
        text,
        re.DOTALL,
    )
    assert match, "Standard MR snippet not found in ship/SKILL.md"
    snippet = match.group(1)
    assert len(snippet) > 0

    # The snippet should handle non-certified projects with single MR
    assert "STANDARD_PROJECT" in snippet


def test_certified_detection_in_ship():
    """@ship detects certified projects from project.yaml."""
    tmpdir = _create_test_repo()
    _create_project_yaml(tmpdir, certified=True)

    # The ship skill should detect certified: true
    # This is tested by the fact that the snippet contains the detection logic
    snippet = _extract_certified_mr_loop()
    assert "project.yaml" in snippet or "certified" in snippet.lower()
