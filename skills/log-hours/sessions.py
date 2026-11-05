"""Summarise a day's agent sessions (Claude Code, Pi, OpenCode) for /log-hours.

Usage: python3 -I sessions.py YYYY-MM-DD

Timestamps are UTC. Per project, prints the active window, the first human
prompts, ticket keys mentioned and half-hour prompt buckets.
"""
import collections
import datetime
import glob
import json
import os
import re
import sqlite3
import sys

SKIP_PREFIXES = ("<", "Another Claude session", "Base directory")

CLAUDE_GLOB = "~/.claude/projects/*/*.jsonl"
PI_GLOB = "~/.pi/agent/sessions/*/*.jsonl"
OPENCODE_DB = "~/.local/share/opencode/opencode.db"

TICKET_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


def label(path):
    """Short project label from a flattened (Claude/Pi) or real (OpenCode) path.

    All three harnesses identify a project by directory; Claude and Pi flatten
    the working directory into the session dir name, OpenCode stores the real
    path. Normalise both to the same label, and derive the home prefix from
    $HOME rather than hardcoding one username.
    """
    flat = path.strip("/-").replace(".", "-").replace("/", "-")
    home = os.path.expanduser("~").strip("/").replace("/", "-").replace(".", "-")
    if flat.startswith(home + "-"):
        flat = flat[len(home) + 1:]
    return re.sub(r"^(?:(?:Documents|Projects)-)+", "", flat, flags=re.IGNORECASE)


def project_of(path):
    """Project label for one Claude Code or Pi session file."""
    return label(os.path.basename(os.path.dirname(path)))


def records(path):
    """Yield (utc_stamp, is_human_prompt, text) for one session file."""
    pi_session = "/.pi/agent/sessions/" in path
    with open(path, errors="replace") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            stamp = event.get("timestamp", "")
            if pi_session:
                if event.get("type") != "message":
                    continue
                message = event.get("message") or {}
                is_prompt = message.get("role") == "user"
            else:
                is_prompt = event.get("type") == "user" and not event.get("isSidechain")
                message = event.get("message") or {}
            yield stamp, is_prompt, text_of(message) if is_prompt else ""


def text_of(message):
    content = message.get("content")
    if isinstance(content, list):
        content = " ".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return content.strip() if isinstance(content, str) else ""


def opencode_records(day):
    """Yield (utc_stamp, is_human_prompt, text) from the OpenCode session DB.

    OpenCode keeps sessions in SQLite rather than JSONL: session_message rows
    carry the role, the epoch millisecond and the message body as JSON.
    """
    path = os.path.expanduser(OPENCODE_DB)
    if not os.path.exists(path):
        return
    start = datetime.datetime.fromisoformat(day + "T00:00:00+00:00")
    end = start + datetime.timedelta(days=1)
    query = """
        select s.directory, m.type, m.time_created, m.data
        from session_message m
        join session_v2 s on s.id = m.session_id
        where m.time_created >= ? and m.time_created < ?
    """
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return
    try:
        rows = conn.execute(
            query, (int(start.timestamp() * 1000), int(end.timestamp() * 1000))
        ).fetchall()
    except sqlite3.Error:
        return
    finally:
        conn.close()
    for directory, kind, millis, data in rows:
        try:
            payload = json.loads(data)
        except ValueError:
            continue
        stamp = datetime.datetime.fromtimestamp(
            millis / 1000, datetime.timezone.utc
        ).isoformat()
        yield label(directory), stamp, kind == "user", text_of(payload)


def main(day):
    windows = collections.defaultdict(list)
    prompts = collections.defaultdict(list)
    buckets = collections.defaultdict(collections.Counter)
    density = collections.defaultdict(collections.Counter)
    keys = collections.defaultdict(collections.Counter)

    def absorb(project, stamp, is_prompt, text):
        if "personal" in project:
            return
        windows[project].append(stamp[11:16])
        density[project][f"{stamp[11:13]}:{int(stamp[14:16]) // 15 * 15:02d}"] += 1
        if not is_prompt or not text or text.startswith(SKIP_PREFIXES):
            return
        hour, minute = int(stamp[11:13]), int(stamp[14:16])
        buckets[project][f"{hour:02d}:{minute // 30 * 30:02d}"] += 1
        if len(prompts[project]) < 6:
            prompts[project].append(f"{stamp[11:16]} {text.replace(chr(10), ' ')[:160]}")
        keys[project].update(TICKET_KEY.findall(text))

    for path in glob.glob(os.path.expanduser(CLAUDE_GLOB)) + glob.glob(
        os.path.expanduser(PI_GLOB)
    ):
        project = project_of(path)
        for stamp, is_prompt, text in records(path):
            if stamp.startswith(day):
                absorb(project, stamp, is_prompt, text)

    for project, stamp, is_prompt, text in opencode_records(day):
        absorb(project, stamp, is_prompt, text)

    if not windows:
        print(f"no sessions for {day}")
        return

    for project in sorted(windows):
        times = windows[project]
        print(f"\n## {project}  {min(times)}-{max(times)}Z  events={len(times)}")
        for prompt in prompts[project]:
            print("  ", prompt)
        if keys[project]:
            print("   keys:", dict(keys[project]))
        if buckets[project]:
            print("   prompts/30min:", dict(sorted(buckets[project].items())))
        print("   events/15min:", dict(sorted(density[project].items())))


if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[1]):
        sys.exit("usage: sessions.py YYYY-MM-DD")
    main(sys.argv[1])
