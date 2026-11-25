#!/usr/bin/env python3
"""The chief of staff's decision log and morning digest (SKILL.md, "A tree of coordinators").

While the owner is away, each decision taken for them goes in the decision log with how to undo
it. The morning digest is drafted from that log and the board's ``## Needs the owner``, and the
owner is sent it by hand, never by a scheduled send: this script has no way to send anything.
It only writes the log and prints a draft.

    decisions.py log --what <text> --why <text> --undo <text> [--by <who>] [--ref <link>]
    decisions.py digest [--all]        # print the draft; changes nothing
    decisions.py sent --via <where>    # after you sent it by hand: marks the log up to here as sent

Reads ``decisions.file`` (the log, beside the board), ``decisions.cos_line`` and ``cos_session``
through ``cos_values``, and the board's path from ``board``. Common options: ``--file`` (the
values file), ``--home`` (the setup's home folder).

The log is Markdown, one ``## <time> <what>`` section per decision with ``Why``, ``Undo``, ``By``
and ``Ref`` bullets, and a ``## sent <time> via <where>`` line each time a digest went out. The
next digest covers only what came after the last ``sent`` line, so a morning's digest never
repeats the one before.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cos_values

HEADER = "# Decision log\n\nEach decision taken for the owner, with how to undo it.\n"
SENT = re.compile(r"^## sent (\S+) via (.+)$")
NO_UNDO = "NO UNDO LINE (add one to the log before sending)"


class LogError(ValueError):
    """A refused write or an unreadable log."""


@dataclass
class Entry:
    time: str
    what: str
    why: str = ""
    undo: str = ""
    by: str = ""
    ref: str = ""


def _now(now: str | None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _one_line(label: str, text: str | None) -> str:
    text = " ".join((text or "").split())
    if not text:
        raise LogError(f"{label} is required: each decision carries what, why and how to undo it")
    return text


def append(path: Path, what: str, why: str, undo: str, *, by="", ref="", now=None) -> Entry:
    """Add a decision. An entry without an undo line is refused, since the skill's rule is
    "with how to undo it"."""
    e = Entry(
        _now(now),
        _one_line("--what", what),
        _one_line("--why", why),
        _one_line("--undo", undo),
        " ".join(by.split()),
        " ".join(ref.split()),
    )
    lines = [f"\n## {e.time} {e.what}", f"- Why: {e.why}", f"- Undo: {e.undo}"]
    lines += [f"- By: {e.by}"] if e.by else []
    lines += [f"- Ref: {e.ref}"] if e.ref else []
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "" if path.exists() and path.stat().st_size else HEADER
    with path.open("a") as f:
        f.write(head + "\n".join(lines) + "\n")
    return e


def read(path: Path) -> tuple[list[Entry], list[Entry], str | None]:
    """Every entry, the entries after the last ``sent`` line, and that line's time."""
    allx: list[Entry] = []
    since: list[Entry] = []
    last_sent: str | None = None
    cur: Entry | None = None
    for line in path.read_text().splitlines() if path.exists() else []:
        if m := SENT.match(line):
            since, cur, last_sent = [], None, m.group(1)
        elif line.startswith("## "):
            time, _, what = line[3:].partition(" ")
            cur = Entry(time, what.strip())
            allx.append(cur)
            since.append(cur)
        elif cur and (m := re.match(r"^- (Why|Undo|By|Ref): (.*)$", line)):
            setattr(cur, m.group(1).lower(), m.group(2).strip())
    return allx, since, last_sent


def needs_the_owner(board: Path) -> list[str]:
    """The top-level bullets of the board's ``## Needs the owner`` (none when there is no board)."""
    if not board.is_file():
        return []
    m = re.search(
        r"^## Needs the owner\n(.*?)(?=^## |\Z)", board.read_text(), re.MULTILINE | re.DOTALL
    )
    return [ln[2:].strip() for ln in (m.group(1) if m else "").splitlines() if ln.startswith("- ")]


def digest(values: cos_values.Values, *, include_sent: bool = False) -> str:
    log = values.path("decisions.file")
    every, entries, last_sent = read(log)
    if include_sent:
        entries = every
    waiting = needs_the_owner(values.path("board"))
    session = values.get("cos_session")
    out = ["# Morning digest (DRAFT, not sent)", ""]
    if line := values.get("decisions.cos_line"):
        out += [line, ""]
    out.append(
        f"Reply in session {session}." if session else "Reply to the chief of staff's own session."
    )
    out += ["", "## Decide first", ""]
    out += [f"- {w}" for w in waiting] or ["- Nothing waits for you."]
    out += ["", "## Decisions taken", ""]
    if last_sent and not include_sent:
        out += [f"Since the digest sent {last_sent}.", ""]
    for e in entries:
        out.append(f"- {e.what} ({e.time}" + (f", by {e.by}" if e.by else "") + ")")
        out.append(f"  - Why: {e.why or '(none)'}")
        out.append(f"  - Undo: {e.undo or NO_UNDO}")
        if e.ref:
            out.append(f"  - Ref: {e.ref}")
    if not entries:
        out.append("- No decision was taken for you.")
    out += [
        "",
        (
            "Not sent. Send it by hand, then run `decisions.py sent --via <where>`; "
            "a scheduled send is never used."
        ),
    ]
    return "\n".join(out) + "\n"


def mark_sent(path: Path, via: str, *, now=None) -> str:
    """Record that the owner was sent the digest, by hand. Nothing is sent here."""
    via = _one_line("--via", via)
    if not path.exists():
        raise LogError(f"{path}: no decision log, so there is no digest to mark as sent")
    t = _now(now)
    with path.open("a") as f:
        f.write(f"\n## sent {t} via {via}\n")
    return t


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The decision log and the morning digest.")
    ap.add_argument("--file", help="the values file")
    ap.add_argument("--home", help="the setup's home folder")
    ap.add_argument("--now", help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("log", help="append a decision with how to undo it")
    g.add_argument("--what")
    g.add_argument("--why")
    g.add_argument("--undo")
    g.add_argument("--by", default="")
    g.add_argument("--ref", default="")
    d = sub.add_parser("digest", help="print the draft digest; it sends nothing")
    d.add_argument("--all", action="store_true", help="include decisions already sent")
    s = sub.add_parser("sent", help="record that you sent the digest by hand")
    s.add_argument("--via")
    a = ap.parse_args(argv)
    try:
        v = cos_values.load(a.file, home=a.home)
        path = v.path("decisions.file")
        if a.cmd == "log":
            e = append(path, a.what, a.why, a.undo, by=a.by, ref=a.ref, now=a.now)
            print(f"logged: {e.what} (undo: {e.undo})")
        elif a.cmd == "digest":
            sys.stdout.write(digest(v, include_sent=a.all))
        else:
            print(f"marked sent {mark_sent(path, a.via, now=a.now)}")
    except (LogError, cos_values.ValuesError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
