#!/usr/bin/env python3
"""A Claude Code PreToolUse hook on Bash: refuse a ``git push`` of a merge of the base into a PR
branch that merges cleanly (#2602).

engineering-loop's lead.md says a lead merges ``origin/main`` into its PR only when ``land`` reports a
conflict, since the merge changes the head, voids the verifier's verdict on it and costs another pass,
and ``land`` merges each head onto main itself. A lead read that and did it anyway, so this is the check
in code. It reads the tool call's JSON on stdin and refuses (exit 2, the reason on stderr, as Claude
Code's PreToolUse contract takes it) a ``git push`` run inside a loop repo (one with
``docs/agents/loop.md``) when all of these hold:

- the checked-out HEAD is a merge of two parents, the second reachable from the base
  (``origin/HEAD``, else ``origin/main``) and the first not: a merge of the base into the branch;
- the first parent merges cleanly with the second (``git merge-tree --write-tree``, exit 0): the merge
  resolved no conflict, so ``land`` would have done it itself.

The one bypass, for the case where ``land`` reported a conflict on that PR: prefix the push with
``LOOP_MERGE_MAIN=<reason>``. A merge that resolved a conflict, and a push that is no merge of the
base, pass. Anything it can't read or parse is allowed (exit 0), so a bug here never blocks work.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heavy_run_guard import SHELL_DEPTH, loop_repo, segments, shell_string, strip_leading

BYPASS = "LOOP_MERGE_MAIN"
REFUSAL = (
    "push_merge_guard: refused, HEAD merges the base into this PR branch, and the PR merges cleanly "
    "into it. `land` merges the head onto main itself, and a merge of main changes the head, which "
    "voids the verifier's verdict and costs another pass (lead.md, step 8). Push without the merge "
    "(reset to the commit before it). If `land` reported `Conflicts in the landing batch` on this PR, "
    f"prefix the push with `{BYPASS}=<why>` to bypass this check."
)


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=8, check=False
    )


def base_ref(cwd: Path) -> str | None:
    head = git(cwd, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head.returncode == 0 and head.stdout.strip():
        return head.stdout.strip()
    return (
        "origin/main"
        if git(cwd, "rev-parse", "--verify", "-q", "origin/main").returncode == 0
        else None
    )


def clean_base_merge(cwd: Path) -> bool:
    """Whether HEAD is a merge of the base into the branch that resolved no conflict."""
    parents = git(cwd, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()[1:]
    if len(parents) != 2 or (base := base_ref(cwd)) is None:
        return False
    first, second = parents
    in_base = lambda sha: git(cwd, "merge-base", "--is-ancestor", sha, base).returncode == 0
    if not in_base(second) or in_base(first):
        return False
    return git(cwd, "merge-tree", "--write-tree", first, second).returncode == 0


def pushing(rest: list[str]) -> tuple[bool, Path | None]:
    """Whether ``rest`` is a ``git push`` (not a deletion), and the directory ``-C`` names."""
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


def judge(command: str, cwd: Path, depth: int = 0) -> bool:
    here: Path | None = cwd
    for words in segments(command):
        rest, _, here = strip_leading(words, here)
        if here is None or not rest:
            continue
        if (inner := shell_string(rest)) is not None:
            if depth < SHELL_DEPTH and judge(inner, here, depth + 1):
                return True
            continue
        bypass = any(re.fullmatch(rf"{BYPASS}=.*\S.*", w) for w in words[: len(words) - len(rest)])
        push, where = pushing(rest)
        if not push or bypass:
            continue
        run_in = (where if where and where.is_absolute() else here / where) if where else here
        if loop_repo(run_in) is not None and clean_base_merge(run_in):
            return True
    return False


def verdict(payload: dict) -> tuple[int, str]:
    if payload.get("tool_name") not in (None, "Bash"):
        return 0, ""
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or "push" not in command:
        return 0, ""
    cwd = Path(payload.get("cwd") or os.getcwd())
    return (2, REFUSAL) if judge(command, cwd) else (0, "")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        code, line = verdict(payload) if isinstance(payload, dict) else (0, "")
    except Exception:  # noqa: BLE001  (a parse bug must never block a command)
        return 0
    if line:
        print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
