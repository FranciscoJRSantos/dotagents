"""Tests for the project-config-detection shared snippet.

The snippet detects whether the current repo is a certified project by checking
for .agents/project.yaml with a certified: true flag. Skills embed this snippet
via begin/end markers and use CERTIFIED_PROJECT vs STANDARD_PROJECT to adjust
behavior (e.g. @ship creates per-slice MRs for certified projects).
"""

import re
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SHIP_SKILL = REPO_ROOT / "skills" / "ship" / "SKILL.md"


def _extract_snippet(skill_file: Path) -> str:
    """Extract the project-config-detection snippet from a skill file."""
    text = skill_file.read_text()
    match = re.search(
        r"<!-- project-config-detection:begin.*?-->\s*```bash\s*\n(.*?)```\s*<!-- project-config-detection:end -->",
        text,
        re.DOTALL,
    )
    assert match, "project-config-detection snippet not found in skill file"
    return match.group(1)


def _run_snippet(snippet: str, project_yaml_content: str | None) -> str:
    """Run the snippet in a temp dir, optionally creating .agents/project.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        if project_yaml_content is not None:
            agents_dir = tmpdir / ".agents"
            agents_dir.mkdir()
            (agents_dir / "project.yaml").write_text(project_yaml_content)
        result = subprocess.run(
            ["bash", "-c", snippet],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        assert result.returncode == 0, f"snippet failed: {result.stderr}"
        assert result.stderr == "", f"snippet stderr: {result.stderr}"
        return result.stdout.strip()


def test_snippet_exists_in_ship_skill():
    """The snippet must be present in @ship's SKILL.md."""
    snippet = _extract_snippet(SHIP_SKILL)
    assert len(snippet) > 0


def test_certified_true_returns_certified_project():
    """certified: true in project.yaml → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "certified: true\n")
    assert output == "CERTIFIED_PROJECT"


def test_certified_false_returns_standard_project():
    """certified: false in project.yaml → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "certified: false\n")
    assert output == "STANDARD_PROJECT"


def test_no_certified_field_returns_standard_project():
    """project.yaml exists but has no certified field → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "name: my-project\n")
    assert output == "STANDARD_PROJECT"


def test_no_project_yaml_returns_standard_project():
    """No .agents/project.yaml → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, None)
    assert output == "STANDARD_PROJECT"


def test_certified_with_extra_fields_returns_certified_project():
    """certified: true among other fields → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "name: aiH\ncertified: true\nstandard: hitrust-e1\n")
    assert output == "CERTIFIED_PROJECT"


def test_certified_true_with_comment_returns_certified_project():
    """certified: true # comment → CERTIFIED_PROJECT (trailing comment ignored)."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "certified: true # hitrust e1\n")
    assert output == "CERTIFIED_PROJECT"


def test_certified_truthy_returns_standard_project():
    """certified: truthy → STANDARD_PROJECT (near-miss rejected by end anchor)."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "certified: truthy\n")
    assert output == "STANDARD_PROJECT"


def test_certified_true_in_comment_returns_standard_project():
    """# certified: true → STANDARD_PROJECT (comment line ignored by ^ anchor)."""
    snippet = _extract_snippet(SHIP_SKILL)
    output = _run_snippet(snippet, "# certified: true\n")
    assert output == "STANDARD_PROJECT"
