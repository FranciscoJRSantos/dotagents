"""Tests for the Conversation Style section in the global rules template and source."""

import re
from pathlib import Path

import pytest

GLOBAL_DIR = Path(__file__).parent.parent / "global"
FILES = [GLOBAL_DIR / "AGENTS.md.example", GLOBAL_DIR / "AGENTS.md"]  # AGENTS.md is gitignored


def section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"missing '## {heading}'"
    return match.group(1)


@pytest.fixture(params=FILES, ids=lambda p: p.name)
def rules(request):
    if not request.param.exists():
        pytest.skip(f"{request.param.name} not present")
    return request.param.read_text()


def test_conversation_style_rules_carry_because_and_precedence_line(rules):
    body = section(rules, "Conversation Style")
    bullets = [l for l in body.splitlines() if l.startswith("- ")]
    rule_bullets = [l for l in bullets if "BECAUSE" in l]
    assert len(rule_bullets) == 7  # 7 BECAUSE rules + the precedence line
    assert len(bullets) == 11  # 8 rules + 3 situation shapes
    assert any("skill defines its own conversation density" in l for l in bullets)


def test_conversation_style_has_shapes_and_example(rules):
    body = section(rules, "Conversation Style")
    for shape in ("Answer:", "Decision needed:", "Work done:"):
        assert shape in body
    assert "Example of the target style" in body


def test_conversation_style_sits_before_model_routing(rules):
    headings = re.findall(r"^## (.+)$", rules, re.M)
    assert headings.index("Self-correction") < headings.index("Conversation Style") < headings.index("Model routing")
