"""Tests for scripts/agents-layout.sh - scan and reorganize legacy .agents/ directories."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
LAYOUT_SCRIPT = SCRIPTS_DIR / "agents-layout.sh"


@pytest.fixture
def repo(tmp_path):
    """Create a temporary git repository."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=tmp_path, capture_output=True
    )
    return tmp_path


@pytest.fixture
def agents_dir(repo):
    """Create a .agents directory structure."""
    agents = repo / ".agents"
    agents.mkdir()
    return agents


def run_layout(args, cwd=None):
    """Run agents-layout.sh with arguments."""
    result = subprocess.run(
        [str(LAYOUT_SCRIPT)] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result


class TestScan:
    """Tests for the scan command."""

    def test_scan_finds_legacy_artifacts(self, agents_dir):
        """scan detects files directly under artifacts/ as legacy."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "main-plan.md").write_text("---\nstatus: active\n---\n")

        result = run_layout(["scan", str(agents_dir.parent)], cwd=agents_dir.parent)
        assert result.returncode == 0
        assert ".agents" in result.stdout
        assert "Legacy files: 1" in result.stdout

    def test_scan_finds_legacy_handoffs(self, agents_dir):
        """scan detects .md files directly under handoffs/ as legacy."""
        handoffs = agents_dir / "handoffs"
        handoffs.mkdir()
        (handoffs / "20241109-123456.md").write_text("# Handoff\n")

        result = run_layout(["scan", str(agents_dir.parent)], cwd=agents_dir.parent)
        assert result.returncode == 0
        assert ".agents" in result.stdout
        assert "Legacy files: 1" in result.stdout

    def test_scan_finds_legacy_state_md(self, agents_dir):
        """scan detects STATE.md as legacy."""
        (agents_dir / "STATE.md").write_text("---\nstatus: active\n---\n")

        result = run_layout(["scan", str(agents_dir.parent)], cwd=agents_dir.parent)
        assert result.returncode == 0
        assert ".agents" in result.stdout
        assert "Legacy files: 1" in result.stdout

    def test_scan_ignores_new_layout(self, agents_dir):
        """scan does not flag the new layout (per-work folders) as legacy."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        work_folder = artifacts / "my-feature"
        work_folder.mkdir()
        (work_folder / "plan.org").write_text("#+TITLE: Plan\n")

        result = run_layout(["scan", str(agents_dir.parent)], cwd=agents_dir.parent)
        assert result.returncode == 0
        assert "No legacy .agents/ directories found" in result.stdout

    def test_scan_counts_open_work(self, agents_dir):
        """scan counts files with status != closed/complete as open work."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "main-plan.md").write_text("---\nstatus: active\n---\n")
        (artifacts / "main-kanban-board.md").write_text("---\nstatus: closed\n---\n")

        result = run_layout(["scan", str(agents_dir.parent)], cwd=agents_dir.parent)
        assert result.returncode == 0
        assert "Legacy files: 2" in result.stdout
        assert "Open work: 1" in result.stdout

    def test_scan_multiple_roots(self, repo):
        """scan accepts multiple root paths."""
        # Create two .agents directories
        agents1 = repo / "project1" / ".agents"
        agents1.mkdir(parents=True)
        (agents1 / "artifacts").mkdir()
        (agents1 / "artifacts" / "main-plan.md").write_text(
            "---\nstatus: active\n---\n"
        )

        agents2 = repo / "project2" / ".agents"
        agents2.mkdir(parents=True)
        (agents2 / "artifacts").mkdir()
        (agents2 / "artifacts" / "main-plan.md").write_text(
            "---\nstatus: active\n---\n"
        )

        result = run_layout(["scan", "project1", "project2"], cwd=repo)
        assert result.returncode == 0
        assert result.stdout.count("Legacy files: 1") == 2


class TestReorganize:
    """Tests for the reorganize command."""

    def test_reorganize_plan_file(self, agents_dir):
        """reorganize moves <label>-plan.md to archive/<label>/plan.md."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "feat-org-artifacts-plan.md").write_text(
            "---\nstatus: active\n---\n"
        )

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        # Check file moved correctly
        assert not (artifacts / "feat-org-artifacts-plan.md").exists()
        assert (agents_dir / "archive" / "feat-org-artifacts" / "plan.md").exists()
        assert (
            agents_dir / "archive" / "feat-org-artifacts" / "plan.md"
        ).read_text() == "---\nstatus: active\n---\n"

    def test_reorganize_kanban_board(self, agents_dir):
        """reorganize moves <label>-kanban-board.md to archive/<label>/kanban-board.md."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "feat-org-artifacts-kanban-board.md").write_text(
            "---\nstatus: active\n---\n"
        )

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (
            agents_dir / "archive" / "feat-org-artifacts" / "kanban-board.md"
        ).exists()

    def test_reorganize_review_impl_renamed(self, agents_dir):
        """reorganize moves <label>-review-impl.md to archive/<label>/review.md (renamed)."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "feat-org-artifacts-review-impl.md").write_text(
            "---\nstatus: clean\n---\n"
        )

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        # Note: review-impl is renamed to review
        assert not (
            agents_dir / "archive" / "feat-org-artifacts" / "review-impl.md"
        ).exists()
        assert (agents_dir / "archive" / "feat-org-artifacts" / "review.md").exists()

    def test_reorganize_impl_progress(self, agents_dir):
        """reorganize moves <label>-impl-progress.md to archive/<label>/impl-progress.md."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "feat-org-artifacts-impl-progress.md").write_text(
            "---\nstatus: in_progress\n---\n"
        )

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (
            agents_dir / "archive" / "feat-org-artifacts" / "impl-progress.md"
        ).exists()

    def test_reorganize_grill_decisions(self, agents_dir):
        """reorganize moves grill-<slug>-decisions.md to archive/<slug>/decisions.md."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "grill-org-artifacts-decisions.md").write_text(
            "---\nartifact: grill-decisions\n---\n"
        )

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (agents_dir / "archive" / "org-artifacts" / "decisions.md").exists()

    def test_reorganize_ticket_prefixed(self, agents_dir):
        """reorganize moves <TICKET>-<rest>.md to archive/<TICKET>/<rest>.md."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "PROJ-123-add-feature.md").write_text("# Add Feature\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (agents_dir / "archive" / "PROJ-123" / "add-feature.md").exists()

    def test_reorganize_misc(self, agents_dir):
        """reorganize moves unmatched files to archive/misc/."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "random-notes.md").write_text("# Notes\n")
        (artifacts / "screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (agents_dir / "archive" / "misc" / "random-notes.md").exists()
        assert (agents_dir / "archive" / "misc" / "screenshot.png").exists()

    def test_reorganize_handoffs(self, agents_dir):
        """reorganize moves handoffs/*.md to archive/handoffs/."""
        handoffs = agents_dir / "handoffs"
        handoffs.mkdir()
        (handoffs / "20241109-123456.md").write_text("# Handoff\n")
        (handoffs / "20241110-090000.md").write_text("# Handoff 2\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (agents_dir / "archive" / "handoffs" / "20241109-123456.md").exists()
        assert (agents_dir / "archive" / "handoffs" / "20241110-090000.md").exists()

    def test_reorganize_state_md(self, agents_dir):
        """reorganize moves STATE.md to archive/STATE.md."""
        (agents_dir / "STATE.md").write_text("---\nstatus: active\n---\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        assert (agents_dir / "archive" / "STATE.md").exists()

    def test_reorganize_dry_run(self, agents_dir):
        """reorganize --dry-run shows what would be done without making changes."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "main-plan.md").write_text("---\nstatus: active\n---\n")

        result = run_layout(
            ["reorganize", str(agents_dir), "--dry-run"], cwd=agents_dir.parent
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout

        # File should still be in place
        assert (artifacts / "main-plan.md").exists()

    def test_reorganize_does_not_overwrite_existing_destination(self, agents_dir):
        """reorganize skips a legacy file whose archive destination already exists."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "feat-app-plan.md").write_text("---\nstatus: active\n")
        dest = agents_dir / "archive" / "feat-app" / "plan.md"
        dest.parent.mkdir(parents=True)
        dest.write_text("already archived\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        # Destination content is untouched, source is left in place, skip counted
        assert dest.read_text() == "already archived\n"
        assert (artifacts / "feat-app-plan.md").exists()
        assert "Files skipped: 1" in result.stdout

    def test_reorganize_removes_empty_directories(self, agents_dir):
        """reorganize removes empty artifacts/ and handoffs/ directories after moving files."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "main-plan.md").write_text("---\nstatus: active\n---\n")

        handoffs = agents_dir / "handoffs"
        handoffs.mkdir()
        (handoffs / "20241109-123456.md").write_text("# Handoff\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        # Empty directories should be removed
        assert not artifacts.exists()
        assert not handoffs.exists()

    def test_reorganize_complex_scenario(self, agents_dir):
        """reorganize handles a complex mix of legacy files."""
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "feat-org-artifacts-plan.md").write_text(
            "---\nstatus: active\n---\n"
        )
        (artifacts / "feat-org-artifacts-kanban-board.md").write_text(
            "---\nstatus: active\n---\n"
        )
        (artifacts / "feat-org-artifacts-review-impl.md").write_text(
            "---\nstatus: clean\n---\n"
        )
        (artifacts / "grill-org-artifacts-decisions.md").write_text(
            "---\nartifact: grill-decisions\n---\n"
        )
        (artifacts / "PROJ-456-fix-bug.md").write_text("# Fix Bug\n")

        handoffs = agents_dir / "handoffs"
        handoffs.mkdir()
        (handoffs / "20241109-123456.md").write_text("# Handoff\n")

        (agents_dir / "STATE.md").write_text("---\nstatus: active\n---\n")

        result = run_layout(["reorganize", str(agents_dir)], cwd=agents_dir.parent)
        assert result.returncode == 0

        # Check all files moved correctly
        assert (agents_dir / "archive" / "feat-org-artifacts" / "plan.md").exists()
        assert (
            agents_dir / "archive" / "feat-org-artifacts" / "kanban-board.md"
        ).exists()
        assert (agents_dir / "archive" / "feat-org-artifacts" / "review.md").exists()
        assert (agents_dir / "archive" / "org-artifacts" / "decisions.md").exists()
        assert (agents_dir / "archive" / "PROJ-456" / "fix-bug.md").exists()
        assert (agents_dir / "archive" / "handoffs" / "20241109-123456.md").exists()
        assert (agents_dir / "archive" / "STATE.md").exists()

        # Check artifacts/ and handoffs/ removed
        assert not (agents_dir / "artifacts").exists()
        assert not (agents_dir / "handoffs").exists()
        assert not (agents_dir / "STATE.md").exists()

    def test_reorganize_from_repo_root(self, repo):
        """reorganize accepts the repo root and finds .agents/ inside."""
        agents_dir = repo / ".agents"
        agents_dir.mkdir()
        artifacts = agents_dir / "artifacts"
        artifacts.mkdir()
        (artifacts / "main-plan.md").write_text("---\nstatus: active\n---\n")

        result = run_layout(["reorganize", str(repo)], cwd=repo)
        assert result.returncode == 0

        assert (agents_dir / "archive" / "main" / "plan.md").exists()
