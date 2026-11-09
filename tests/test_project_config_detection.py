"""Tests for the project-config-detection shared snippet.

The snippet detects whether the current repo is a certified project by checking
for .agents/project.yaml with a certified: true flag. Skills embed this snippet
via begin/end markers and use CERTIFIED_PROJECT vs STANDARD_PROJECT to adjust
behavior (e.g. @ship creates per-slice MRs for certified projects).

Three states:
- CERTIFIED_PROJECT: certified: true/True/TRUE found
- STANDARD_PROJECT: no project.yaml, or certified: false/False/FALSE, or no certified line
- exit 1: certified line exists but value not recognized (prevents silent fallback)
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


def _extract_all_snippets(skill_file: Path) -> list[str]:
    """Extract all project-config-detection snippets from a skill file."""
    text = skill_file.read_text()
    # Try to extract with ```bash wrapper first (for @ship)
    snippets = re.findall(
        r"<!-- project-config-detection:begin.*?-->\s*```bash\s*\n(.*?)```\s*<!-- project-config-detection:end -->",
        text,
        re.DOTALL,
    )
    if snippets:
        return snippets

    # If no ```bash wrapper found, extract without wrapper (for @build 2a section)
    return re.findall(
        r"<!-- project-config-detection:begin.*?-->\s*(.*?)\s*<!-- project-config-detection:end -->",
        text,
        re.DOTALL,
    )


def _run_snippet(
    snippet: str, project_yaml_content: str | None
) -> tuple[int, str, str]:
    """Run the snippet in a temp dir. Returns (returncode, stdout, stderr)."""
    # The snippet assigns PROJECT_TYPE instead of echoing it, so append an echo
    # to capture the variable for assertion
    snippet_with_echo = snippet + '\necho "$PROJECT_TYPE"'
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        if project_yaml_content is not None:
            agents_dir = tmpdir / ".agents"
            agents_dir.mkdir()
            (agents_dir / "project.yaml").write_text(project_yaml_content)
        result = subprocess.run(
            ["bash", "-c", snippet_with_echo],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        return result.returncode, result.stdout.strip(), result.stderr


def _assert_certified(snippet: str, content: str | None, expected: str):
    """Run snippet and assert it returns expected stdout with exit 0."""
    rc, stdout, stderr = _run_snippet(snippet, content)
    assert rc == 0, f"snippet exited {rc}: {stderr}"
    assert stdout == expected, f"expected {expected}, got {stdout}"


def _assert_unparseable(snippet: str, content: str):
    """Run snippet and assert it exits 1 with error on stderr."""
    rc, stdout, stderr = _run_snippet(snippet, content)
    assert rc == 1, f"snippet should exit 1 but exited {rc}: stdout={stdout}"
    assert "not recognized" in stderr.lower() or "error" in stderr.lower(), (
        f"stderr should contain error message: {stderr}"
    )


# --- Snippet presence ---


def test_snippet_exists_in_ship_skill():
    """The snippet must be present in @ship's SKILL.md."""
    snippet = _extract_snippet(SHIP_SKILL)
    assert len(snippet) > 0


def test_all_three_snippets_are_byte_identical():
    """All three copies (2 in @ship, 1 in @build) must be byte-identical."""
    ship_snippets = _extract_all_snippets(SHIP_SKILL)
    assert len(ship_snippets) == 2, (
        f"@ship should have 2 copies of the detection snippet, found {len(ship_snippets)}"
    )

    build_skill = REPO_ROOT / "skills" / "build" / "SKILL.md"
    build_snippets = _extract_all_snippets(build_skill)
    assert len(build_snippets) == 1, (
        f"@build should have 1 copy of the detection snippet, found {len(build_snippets)}"
    )

    # Normalize trailing whitespace before comparing (markdown extraction varies)
    normalized = [s.rstrip() for s in ship_snippets + build_snippets]

    # All three must be byte-identical (after normalization)
    assert normalized[0] == normalized[1], (
        "@ship's two copies of the detection snippet differ"
    )
    assert normalized[0] == normalized[2], (
        "@ship and @build copies of the detection snippet differ"
    )


# --- CERTIFIED_PROJECT cases ---


def test_certified_true_returns_certified_project():
    """certified: true in project.yaml → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "certified: true\n", "CERTIFIED_PROJECT")


def test_certified_true_uppercase():
    """certified: True → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "certified: True\n", "CERTIFIED_PROJECT")


def test_certified_true_all_caps():
    """certified: TRUE → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "certified: TRUE\n", "CERTIFIED_PROJECT")


def test_certified_with_extra_fields_returns_certified_project():
    """certified: true among other fields → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(
        snippet,
        "name: aiH\ncertified: true\nstandard: hitrust-e1\n",
        "CERTIFIED_PROJECT",
    )


def test_certified_true_with_comment_returns_certified_project():
    """certified: true # comment → CERTIFIED_PROJECT (trailing comment ignored)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "certified: true # hitrust e1\n", "CERTIFIED_PROJECT")


# --- STANDARD_PROJECT cases ---


def test_certified_false_returns_standard_project():
    """certified: false in project.yaml → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "certified: false\n", "STANDARD_PROJECT")


def test_certified_false_uppercase():
    """certified: False → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "certified: False\n", "STANDARD_PROJECT")


def test_no_certified_field_returns_standard_project():
    """project.yaml exists but has no certified field → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "name: my-project\n", "STANDARD_PROJECT")


def test_no_project_yaml_returns_standard_project():
    """No .agents/project.yaml → STANDARD_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, None, "STANDARD_PROJECT")


def test_certified_true_in_comment_returns_standard_project():
    """# certified: true → STANDARD_PROJECT (comment line ignored by ^ anchor)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_certified(snippet, "# certified: true\n", "STANDARD_PROJECT")


# --- UNPARSEABLE cases (exit 1 — prevents silent fallback to batched MR) ---


def test_certified_truthy_exits_unparseable():
    """certified: truthy → exit 1 (not a recognized boolean)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_unparseable(snippet, "certified: truthy\n")


def test_certified_quoted_true_exits_unparseable():
    """certified: "true" → exit 1 (quoted string, not bare boolean)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_unparseable(snippet, 'certified: "true"\n')


def test_certified_yes_exits_unparseable():
    """certified: yes → exit 1 (YAML 1.1 boolean not supported)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_unparseable(snippet, "certified: yes\n")


def test_certified_on_exits_unparseable():
    """certified: on → exit 1 (YAML 1.1 boolean not supported)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_unparseable(snippet, "certified: on\n")


def test_certified_1_exits_unparseable():
    """certified: 1 → exit 1 (numeric not supported)."""
    snippet = _extract_snippet(SHIP_SKILL)
    _assert_unparseable(snippet, "certified: 1\n")


def test_crlf_line_endings_handled():
    """certified: true with CRLF line endings → CERTIFIED_PROJECT."""
    snippet = _extract_snippet(SHIP_SKILL)
    # CRLF: the regex anchor $ in POSIX grep matches before \r on some systems
    # but our regex explicitly handles it via ([[:space:]]*#.*)?$ which absorbs \r
    _assert_certified(snippet, "certified: true\r\n", "CERTIFIED_PROJECT")
