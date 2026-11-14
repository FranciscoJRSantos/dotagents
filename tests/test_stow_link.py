"""Tests for `make link`: stow packages replace the manifest-based deploy.

Each test copies the repo sources into tmp_path and runs make there with HOME
pointed at a throwaway home, so the live ~/.config, ~/.claude and ~/.agents are
never touched.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ["Makefile", "scripts", "skills", "agents", "plugins", "bin", "global"]
SKIP = shutil.ignore_patterns(".git", "__pycache__", "node_modules", ".pytest_cache")

def _has_mikefarah_yq():
    if not shutil.which("yq"):
        return False
    out = subprocess.run(["yq", "--version"], capture_output=True, text=True)
    return "mikefarah" in out.stdout + out.stderr


pytestmark = pytest.mark.skipif(
    not (shutil.which("stow") and _has_mikefarah_yq()), reason="needs stow and mikefarah yq"
)


@pytest.fixture
def env(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in SOURCES:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, repo / name, ignore=SKIP)
        else:
            shutil.copy(src, repo / name)
    # global/AGENTS.md is gitignored; the example stands in for it
    shutil.copy(repo / "global" / "AGENTS.md.example", repo / "global" / "AGENTS.md")
    home = tmp_path / "home"
    home.mkdir()
    return repo, home


def make(repo, home, *targets):
    return subprocess.run(
        ["make", *targets],
        cwd=repo,
        env={**os.environ, "HOME": str(home)},
        capture_output=True,
        text=True,
    )


def seed_old_deploy(repo, home):
    """Recreate what the rsync/manifest deploy left behind, plus unmanaged entries."""
    oc, cl, ag = home / ".config/opencode", home / ".claude", home / ".agents"
    skills = sorted(p.name for p in (repo / "skills").iterdir() if p.is_dir())
    agents = sorted(p.name for p in (repo / "agents").glob("*.md"))
    for target, names, src in [
        (oc / "skills", skills, repo / "skills"),
        (cl / "skills", skills, repo / "skills"),
        (oc / "agents", agents, repo / "agents"),
        (cl / "agents", agents, repo / "agents"),
    ]:
        target.mkdir(parents=True)
        for n in names:
            s = src / n
            shutil.copytree(s, target / n) if s.is_dir() else shutil.copy(s, target / n)
        (target / ".personal-agents-manifest").write_text("\n".join(names) + "\n")
    (oc / "plugins").mkdir()
    shutil.copytree(repo / "plugins/bg-tasks", oc / "plugins/bg-tasks")
    (oc / "plugins/.personal-agents-manifest").write_text("bg-tasks\n")
    (oc / "plugins/nono-sandbox.ts").symlink_to("/nonexistent/nono-sandbox.ts")
    (oc / "AGENTS.md").write_text("old deployed rules\n")
    (cl / "skills/synced").mkdir()
    (cl / "skills/synced/keep.txt").write_text("harness-owned")
    (ag / "bin").mkdir(parents=True)
    shutil.copy(repo / "bin/slug", ag / "bin/slug")
    shutil.copytree(repo / "agents/partials", ag / "partials")
    (ag / ".personal-agents-manifest").write_text("bin\npartials\n")
    (ag / "artifacts").mkdir()
    (ag / "artifacts/keep.txt").write_text("user work")


def test_link_replaces_deploy_with_resolving_symlinks(env):
    repo, home = env
    seed_old_deploy(repo, home)
    r = make(repo, home, "link")
    assert r.returncode == 0, r.stdout + r.stderr

    oc, cl, ag = home / ".config/opencode", home / ".claude", home / ".agents"
    for skills_dir in (oc / "skills", cl / "skills"):
        for skill in (repo / "skills").iterdir():
            link = skills_dir / skill.name
            assert link.is_symlink(), link
            assert link.resolve() == skill.resolve()
            assert (link / "SKILL.md").exists()
    assert (oc / "agents/reviewer.md").resolve() == (repo / "agents/reviewer.md").resolve()
    assert (cl / "agents/reviewer.md").resolve() == (repo / "build/claude-agents/reviewer.md").resolve()
    assert "model: inherit" in (cl / "agents/reviewer.md").read_text()
    assert (oc / "plugins/bg-tasks").resolve() == (repo / "plugins/bg-tasks").resolve()
    assert (oc / "AGENTS.md").resolve() == (repo / "global/AGENTS.md").resolve()
    assert (ag / "bin/slug").resolve() == (repo / "bin/slug").resolve()
    assert (ag / "partials").resolve() == (repo / "agents/partials").resolve()

    # real directories are kept (no folding), so harness-owned entries stay out of the repo
    for d in (oc / "skills", cl / "skills", oc / "agents", cl / "agents", ag / "bin"):
        assert d.is_dir() and not d.is_symlink(), d
    # manifests are retired
    assert not list(home.rglob(".personal-agents-manifest"))


def test_link_leaves_unmanaged_entries_alone(env):
    repo, home = env
    seed_old_deploy(repo, home)
    assert make(repo, home, "link").returncode == 0
    assert (home / ".claude/skills/synced/keep.txt").read_text() == "harness-owned"
    assert (home / ".agents/artifacts/keep.txt").read_text() == "user work"
    nono = home / ".config/opencode/plugins/nono-sandbox.ts"
    assert nono.is_symlink() and os.readlink(nono) == "/nonexistent/nono-sandbox.ts"


def test_link_is_idempotent_and_backs_up_changed_global_rules(env):
    repo, home = env
    seed_old_deploy(repo, home)
    assert make(repo, home, "link").returncode == 0
    assert make(repo, home, "link").returncode == 0
    backup = home / ".config/opencode/AGENTS.md.pre-stow"
    assert backup.read_text() == "old deployed rules\n"


def test_relink_removes_links_of_deleted_sources(env):
    repo, home = env
    assert make(repo, home, "link").returncode == 0
    shutil.rmtree(repo / "skills/ship")
    (repo / "agents/reviewer.md").unlink()
    assert make(repo, home, "link").returncode == 0
    assert not (home / ".config/opencode/skills/ship").is_symlink()
    assert not (home / ".claude/skills/ship").is_symlink()
    assert not (home / ".config/opencode/agents/reviewer.md").is_symlink()
    assert not (home / ".claude/agents/reviewer.md").is_symlink()
    dangling = [p for p in home.rglob("*") if p.is_symlink() and not p.exists()]
    assert dangling == []


def test_lint_links_fails_on_broken_link(env):
    repo, home = env
    assert make(repo, home, "link").returncode == 0
    assert make(repo, home, "lint-links").returncode == 0
    (repo / "stow/opencode/.config/opencode/skills/ghost").symlink_to("../../../../../skills/ghost")
    # the make target regenerates stow/ first, so call the check itself on the broken tree
    r = subprocess.run(
        [str(repo / "scripts/lint-stow-links.sh")], capture_output=True, text=True
    )
    assert r.returncode != 0
    assert "ghost" in r.stdout + r.stderr


def test_deploy_targets_are_gone(env):
    repo, home = env
    for target in ("deploy", "drift"):
        assert make(repo, home, "-n", target).returncode != 0
    assert not (repo / "scripts/manifest-sync.sh").exists()
    assert not (repo / "scripts/deploy-agents.sh").exists()


def snapshot(home):
    return sorted(
        (str(p.relative_to(home)), os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None)
        for p in home.rglob("*")
    )


def test_dry_run_leaves_home_untouched(env):
    repo, home = env
    seed_old_deploy(repo, home)
    before = snapshot(home)
    r = make(repo, home, "link", "DRY_RUN=1")
    assert r.returncode == 0, r.stdout + r.stderr
    assert snapshot(home) == before


def test_hostile_manifest_entries_delete_nothing_outside_the_target(env):
    repo, home = env
    seed_old_deploy(repo, home)
    precious = home / "precious"
    precious.write_text("keep me")
    sibling = home / ".claude/skills/../sibling-dir"
    sibling.mkdir()
    manifest = home / ".claude/skills/.personal-agents-manifest"
    manifest.write_text(manifest.read_text() + "../../precious\n..\n../sibling-dir\n")
    r = make(repo, home, "link")
    assert r.returncode == 0, r.stdout + r.stderr
    assert precious.read_text() == "keep me"
    assert sibling.is_dir()
    assert "skipping unsafe manifest entry" in r.stdout + r.stderr


def test_symlinked_target_dir_is_refused(env):
    repo, home = env
    seed_old_deploy(repo, home)
    real = home / "elsewhere"
    shutil.move(home / ".claude/agents", real)
    (home / ".claude/agents").symlink_to(real)
    r = make(repo, home, "link")
    assert r.returncode != 0
    assert "symlink" in r.stdout + r.stderr
    assert (real / "reviewer.md").exists()


def test_edited_deployed_copy_is_backed_up_not_deleted(env):
    repo, home = env
    seed_old_deploy(repo, home)
    (home / ".config/opencode/skills/arch/local-note.md").write_text("my edit")
    r = make(repo, home, "link")
    assert r.returncode == 0, r.stdout + r.stderr
    backups = list(home.glob(".local/state/dotagents-pre-stow/*/.config/opencode/skills/arch/local-note.md"))
    assert len(backups) == 1 and backups[0].read_text() == "my edit"
    # unmodified copies are simply removed, not backed up
    assert not list(home.glob(".local/state/dotagents-pre-stow/*/.config/opencode/skills/ship"))


def test_unmanaged_file_colliding_with_a_link_fails_loudly(env):
    repo, home = env
    (home / ".claude/agents").mkdir(parents=True)
    (home / ".claude/agents/reviewer.md").write_text("hand made")
    r = make(repo, home, "link")
    assert r.returncode != 0
    assert (home / ".claude/agents/reviewer.md").read_text() == "hand made"
