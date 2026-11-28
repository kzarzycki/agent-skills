#!/usr/bin/env python3
"""A Claude Code PreToolUse hook on Bash: refuse a ``git push`` to a held PR's branch and a PR created for a held
issue (#2998).

A hold or stop sent to a lead mid-turn is read only after the turn in flight ends, so a hold that lives in a message
loses the race: the lead still pushes or opens a PR. A hold is the ``loop:hold`` label on the PR or issue, which
gatekeeper's ``hold <n>`` sets (the manager's stop or hold command), and this hook is the check in code. It reads the
tool call's JSON on stdin and refuses (exit 2, the reason on stderr, as Claude Code's PreToolUse contract takes it),
inside a loop repo (one with ``docs/agents/loop.md``):

- a ``git push`` (not a deletion) of a branch whose open PR carries ``loop:hold``, or whose PR body closes an issue
  that carries it;
- a PR created (``gh pr create``, or a POST to ``.../pulls``) whose body closes an issue that carries it.

The refusal names the hold and who set it (the label's last ``labeled`` event). Removing the label lifts it: the next
call reads the label again, so nothing is cached. The label is read with ``gh api``; anything the hook can't read or
parse is allowed (exit 0), so a bug or an offline run never blocks work.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heavy_run_guard import LOOP_FILE, SHELL_DEPTH, repo_root, segments, shell_string, strip_leading

HOLD = "loop:hold"
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)[ \t]+#(\d+)", re.IGNORECASE)
REMOTE = re.compile(r"github\.com[:/]+([^/\s]+/[^/\s]+?)(?:\.git)?/?$")


def run(cwd: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=8, check=False)


def repo_of(cwd: Path) -> str | None:
    """``owner/name`` of the checkout's ``origin``, else None."""
    out = run(cwd, "git", "remote", "get-url", "origin")
    match = REMOTE.search(out.stdout.strip()) if out.returncode == 0 else None
    return match[1] if match else None


def api(cwd: Path, path: str, *fields: str):
    out = run(cwd, "gh", "api", "-X", "GET", path, *fields)
    return json.loads(out.stdout) if out.returncode == 0 else None


def setter(cwd: Path, repo: str, number: int) -> str:
    """Who put the label on, from the last ``labeled`` event naming it; ``unknown`` when it can't be read."""
    events = api(cwd, f"repos/{repo}/issues/{number}/events", "-f", "per_page=100")
    for event in reversed(events if isinstance(events, list) else []):
        if event.get("event") == "labeled" and (event.get("label") or {}).get("name") == HOLD:
            return (event.get("actor") or {}).get("login") or "unknown"
    return "unknown"


def held(cwd: Path, repo: str, number: int) -> str | None:
    """The refusal line when issue or PR ``number`` carries the hold, else None."""
    node = api(cwd, f"repos/{repo}/issues/{number}")
    if not isinstance(node, dict):
        return None
    if HOLD not in {str(x.get("name")) for x in node.get("labels") or []}:
        return None
    return (
        f"hold_guard: refused, #{number} is held (`{HOLD}`, set by @{setter(cwd, repo, number)}): stop and report. "
        f"The hold is the label, not a message; it lifts only when the label is removed."
    )


def closed_issues(text: str) -> list[int]:
    return [int(n) for n in CLOSES.findall(text or "")]


def push_branch(rest: list[str], cwd: Path) -> str | None:
    """The branch a ``git push`` sends: the destination of its refspec, else the checked-out branch."""
    args = rest[rest.index("push") + 1 :]
    words = [a for a in args if not a.startswith("-")]
    if len(words) >= 2:
        dst = words[1].split(":")[-1]
        dst = dst.removeprefix("refs/heads/")
        if dst and dst != "HEAD":
            return dst
    out = run(cwd, "git", "symbolic-ref", "--short", "HEAD")
    return out.stdout.strip() or None if out.returncode == 0 else None


def pushing(rest: list[str]) -> tuple[bool, Path | None]:
    if not rest or Path(rest[0]).name != "git":
        return False, None
    i, where = 1, None
    while i < len(rest) and rest[i].startswith("-"):
        if rest[i] == "-C" and i + 1 < len(rest):
            where = Path(rest[i + 1])
            i += 2
        else:
            i += 2 if rest[i] in ("-c", "--git-dir", "--work-tree") else 1
    args = rest[i + 1 :]
    return rest[i : i + 1] == ["push"] and not any(a in ("--delete", "-d") for a in args), where


def create_body(rest: list[str], cwd: Path) -> tuple[bool, str, str | None]:
    """Whether ``rest`` creates a PR, the body it sends, and the repo it names (``--repo``, else None)."""
    if rest[:1] and Path(rest[0]).name == "gh" and rest[1:3] == ["pr", "create"]:
        body, repo, i = "", None, 3
        while i < len(rest):
            word = rest[i]
            flag, eq, value = word.partition("=")
            if flag in ("--body", "-b", "--body-file", "-F", "--repo", "-R") and not eq:
                value = rest[i + 1] if i + 1 < len(rest) else ""
                i += 1
            if flag in ("--body", "-b"):
                body += value + "\n"
            elif flag in ("--body-file", "-F") and value:
                try:
                    body += (cwd / value).read_text(errors="replace") + "\n"
                except OSError:
                    pass
            elif flag in ("--repo", "-R"):
                repo = value
            i += 1
        return True, body, repo
    if (
        rest[:1]
        and Path(rest[0]).name == "curl"
        and any(re.search(r"/repos/([^/\s]+/[^/\s]+)/pulls/?$", w) for w in rest)
    ):
        url = next(w for w in rest if re.search(r"/repos/[^/\s]+/[^/\s]+/pulls/?$", w))
        repo = re.search(r"/repos/([^/\s]+/[^/\s]+)/pulls", url)[1]  # type: ignore[index]
        body = ""
        for j, w in enumerate(rest):
            if w in ("-d", "--data", "--data-raw", "--data-binary") and j + 1 < len(rest):
                data = rest[j + 1]
                try:
                    body += str(json.loads(data).get("body") or "") + "\n"
                except (ValueError, AttributeError):
                    body += data + "\n"
        return True, body, repo
    return False, "", None


def judge(command: str, cwd: Path, depth: int = 0) -> str:
    here: Path | None = cwd
    for words in segments(command):
        rest, _, here = strip_leading(words, here)
        if here is None or not rest:
            continue
        if (inner := shell_string(rest)) is not None:
            if depth < SHELL_DEPTH and (line := judge(inner, here, depth + 1)):
                return line
            continue
        push, where = pushing(rest)
        run_in = (where if where and where.is_absolute() else here / where) if where else here
        root = repo_root(run_in)
        if root is None or not (root / LOOP_FILE).is_file():
            continue
        if push:
            repo, branch = repo_of(run_in), push_branch(rest, run_in)
            if not repo or not branch:
                continue
            owner = repo.split("/")[0]
            pulls = api(
                run_in, f"repos/{repo}/pulls", "-f", f"head={owner}:{branch}", "-f", "state=open"
            )
            for pull in pulls if isinstance(pulls, list) else []:
                numbers = [pull.get("number"), *closed_issues(pull.get("body") or "")]
                for number in filter(None, numbers):
                    if line := held(run_in, repo, int(number)):
                        return line
            continue
        creates, body, named = create_body(rest, run_in)
        if creates and (repo := named or repo_of(run_in)):
            for number in closed_issues(body):
                if line := held(run_in, repo, number):
                    return line
    return ""


def verdict(payload: dict) -> tuple[int, str]:
    if payload.get("tool_name") not in (None, "Bash"):
        return 0, ""
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not re.search(r"push|pr create|pulls", command):
        return 0, ""
    line = judge(command, Path(payload.get("cwd") or os.getcwd()))
    return (2, line) if line else (0, "")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        code, line = verdict(payload) if isinstance(payload, dict) else (0, "")
    except Exception:  # noqa: BLE001  (a parse or network bug must never block a command)
        return 0
    if line:
        print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
