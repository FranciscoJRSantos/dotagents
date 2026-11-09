"""Tests for skills/arch/md_to_adf.py.

The converter turns the known subset of markdown produced by /arch's templates into
Atlassian Document Format (ADF) JSON. These tests pin the cases that used to hang the
converter or that /arch relies on.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "arch"))

import md_to_adf  # noqa: E402


def _content(doc):
    return doc["content"]


def test_headings_all_levels():
    md = "\n".join(f"{'#' * n} Heading{n}" for n in range(1, 7))
    doc = md_to_adf.markdown_to_adf(md)
    headings = _content(doc)
    assert len(headings) == 6
    for n, node in enumerate(headings, start=1):
        assert node["type"] == "heading"
        assert node["attrs"]["level"] == n
        assert node["content"][0]["text"] == f"Heading{n}"


def test_fence_with_hash_comment_becomes_code_block():
    md = "```python\n# comment\nx = 1\n```"
    doc = md_to_adf.markdown_to_adf(md)
    nodes = _content(doc)
    assert len(nodes) == 1
    assert nodes[0]["type"] == "codeBlock"
    assert nodes[0]["attrs"]["language"] == "python"
    assert nodes[0]["content"][0]["text"] == "# comment\nx = 1"


def test_table():
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    doc = md_to_adf.markdown_to_adf(md)
    nodes = _content(doc)
    assert len(nodes) == 1
    table = nodes[0]
    assert table["type"] == "table"
    rows = table["content"]
    assert len(rows) == 2
    header = rows[0]["content"]
    body = rows[1]["content"]
    assert header[0]["type"] == "tableHeader"
    assert header[0]["content"][0]["content"][0]["text"] == "A"
    assert header[1]["content"][0]["content"][0]["text"] == "B"
    assert body[0]["type"] == "tableCell"
    assert body[0]["content"][0]["content"][0]["text"] == "1"
    assert body[1]["content"][0]["content"][0]["text"] == "2"


def test_lists():
    md = "- a\n- b\n1. one\n2. two"
    doc = md_to_adf.markdown_to_adf(md)
    nodes = _content(doc)
    assert [n["type"] for n in nodes] == ["bulletList", "orderedList"]
    bullet_items = nodes[0]["content"]
    ordered_items = nodes[1]["content"]
    assert [i["content"][0]["content"][0]["text"] for i in bullet_items] == ["a", "b"]
    assert [i["content"][0]["content"][0]["text"] for i in ordered_items] == [
        "one",
        "two",
    ]


def test_bold_and_code_inline():
    md = "**bold** and `code`"
    doc = md_to_adf.markdown_to_adf(md)
    nodes = _content(doc)
    assert len(nodes) == 1
    paragraph = nodes[0]
    assert paragraph["type"] == "paragraph"
    content = paragraph["content"]
    assert len(content) == 3
    assert content[0]["text"] == "bold"
    assert content[0]["marks"] == [{"type": "strong"}]
    assert content[1]["text"] == " and "
    assert content[2]["text"] == "code"
    assert content[2]["marks"] == [{"type": "code"}]


def test_empty_input():
    doc = md_to_adf.markdown_to_adf("")
    assert doc == {"version": 1, "type": "doc", "content": []}
