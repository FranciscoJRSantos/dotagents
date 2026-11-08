#!/usr/bin/env python3
"""Convert markdown text to Atlassian Document Format (ADF) JSON for Jira comments.

Usage: python3 md_to_adf.py <input.md> [output.json]
If output is omitted, prints to stdout.
"""

import json
import re
import sys


def parse_inline(text: str) -> list[dict]:
    """Parse inline markdown (code spans, bold) into ADF text nodes."""
    nodes = []
    # Match inline code `...` or bold **...**
    pattern = r'(``[^`]*``|`[^`]*`|\*\*[^*]*\*\*)'
    last_end = 0
    for match in re.finditer(pattern, text):
        if match.start() > last_end:
            nodes.append({"type": "text", "text": text[last_end:match.start()]})
        content = match.group(0)
        if content.startswith('``') and content.endswith('``'):
            nodes.append({"type": "text", "text": content[2:-2], "marks": [{"type": "code"}]})
        elif content.startswith('`') and content.endswith('`'):
            nodes.append({"type": "text", "text": content[1:-1], "marks": [{"type": "code"}]})
        elif content.startswith('**') and content.endswith('**'):
            nodes.append({"type": "text", "text": content[2:-2], "marks": [{"type": "strong"}]})
        last_end = match.end()
    if last_end < len(text):
        nodes.append({"type": "text", "text": text[last_end:]})
    if not nodes:
        nodes.append({"type": "text", "text": text})
    return nodes


def make_paragraph(text: str) -> dict:
    return {"type": "paragraph", "content": parse_inline(text)}


def make_heading(level: int, text: str) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": parse_inline(text)}


def make_code_block(language: str, text: str) -> dict:
    attrs = {"language": language} if language else {}
    return {"type": "codeBlock", "attrs": attrs, "content": [{"type": "text", "text": text}]}


def make_list_item(text: str) -> dict:
    return {"type": "listItem", "content": [make_paragraph(text)]}


def make_table(rows: list[list[str]]) -> dict:
    table_content = []
    for i, row in enumerate(rows):
        cells = []
        for cell in row:
            cell_type = "tableHeader" if i == 0 else "tableCell"
            cells.append({
                "type": cell_type,
                "attrs": {},
                "content": [make_paragraph(cell.strip())]
            })
        table_content.append({"type": "tableRow", "content": cells})
    return {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": table_content
    }


def markdown_to_adf(markdown_text: str) -> dict:
    lines = markdown_text.split('\n')
    content: list[dict] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.strip() == '':
            i += 1
            continue

        if line.startswith('```'):
            language = line[3:].strip().strip('`')
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # closing fence
            content.append(make_code_block(language, '\n'.join(code_lines)))
            continue

        heading = re.match(r'^(#{1,6})\s+(.*)$', line)
        if heading:
            content.append(make_heading(len(heading.group(1)), heading.group(2)))
            i += 1
            continue

        if re.match(r'^\d+\.\s', line):
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s', lines[i]):
                text = re.sub(r'^\d+\.\s', '', lines[i])
                items.append(make_list_item(text))
                i += 1
            content.append({"type": "orderedList", "content": items})
            continue

        if line.startswith('- '):
            items = []
            while i < len(lines) and lines[i].startswith('- '):
                text = lines[i][2:]
                items.append(make_list_item(text))
                i += 1
            content.append({"type": "bulletList", "content": items})
            continue

        if '|' in line and not line.startswith('- ') and not re.match(r'^\d+\.\s', line):
            table_lines = []
            while i < len(lines) and '|' in lines[i] and not lines[i].startswith('- ') and not re.match(r'^\d+\.\s', lines[i]):
                table_lines.append(lines[i])
                i += 1
            rows = []
            for tl in table_lines:
                if re.match(r'^\s*\|[-\s|]+\|\s*$', tl):
                    continue
                cells = [c.strip() for c in tl.split('|')[1:-1]]
                if cells:
                    rows.append(cells)
            if rows:
                content.append(make_table(rows))
            continue

        para_lines = []
        while (i < len(lines) and lines[i].strip() != '' and
               not lines[i].startswith('```') and
               not re.match(r'^#{1,6}\s+', lines[i]) and
               not lines[i].startswith('- ') and
               not re.match(r'^\d+\.\s', lines[i])):
            para_lines.append(lines[i])
            i += 1
        if not para_lines:
            # A non-blank line reached here that no earlier block consumed (e.g. a
            # stray `#` not matching the heading pattern). Consume at least one line so
            # the loop always advances.
            para_lines.append(lines[i])
            i += 1
        para_text = ' '.join(para_lines)
        content.append(make_paragraph(para_text))

    return {"version": 1, "type": "doc", "content": content}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: md_to_adf.py <input.md> [output.json]", file=sys.stderr)
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        md = f.read()

    adf = markdown_to_adf(md)

    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'w') as f:
            json.dump(adf, f, indent=2)
    else:
        print(json.dumps(adf, indent=2))
