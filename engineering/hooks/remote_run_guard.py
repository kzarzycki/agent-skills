#!/usr/bin/env python3
"""A Claude Code PreToolUse hook on Bash: refuse a build, test, gate, land or git push run on
another machine over ssh (#1754).

Work for a host runs in an agent session on that host, or in a Claude cloud session, so it stays
visible, resumable and on the owner's board (orchestrating-agents' SKILL.md, Rules). An
``ssh <host> <build>`` from a session elsewhere hides it: nothing tracks it, and its output lives
only in the caller's context. This hook reads the tool call's JSON on stdin and refuses (exit 2,
the reason on stderr, as Claude Code's PreToolUse contract takes it) a command one of whose
segments is ``ssh [options] <host> <remote command>`` or orchestrating-agents'
``omnigent_agent.py ssh <host> [--why <purpose>] -- <command>``, when a segment of the remote
command, read as the remote shell reads it, builds or tests (``BUILD_TOOLS`` and the like), runs a
gate or a land (``GATE_SCRIPTS`` with a ``GATE_SUBCOMMANDS`` word), or pushes git.

Everything else over ssh stays allowed: reading a log (``cat``, ``tail``, ``grep``), ``git
log``/``status``/``rev-parse``, ``/proc/loadavg``, ``ps``, ``df``, ``approvals.py check``. Those read a
host's state and end at once, so they leave no run to track and no result anyone resumes. It is a
deny list, so host maintenance it does not know keeps working.

It reuses ``heavy_run_guard.py``'s shell parsing, which ships beside it. Anything it can't read or
parse is allowed (exit 0), so a bug here never blocks work. Stdlib only, no subprocess: it runs on
every Bash call.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from heavy_run_guard import (  # its sibling, deployed with it
        after_uv_run,
        python_m_pytest,
        segments,
        shell_string,
        strip_leading,
    )
except Exception:  # noqa: BLE001  (without its sibling the hook judges nothing, never blocks)
    sys.exit(0)

SHELL_DEPTH = 3  # nested ``sh -c`` strings judged, locally and remotely; deeper ones are allowed
# ssh's options that take a value (ssh(1)); every other letter is a flag
SSH_VALUED = set("BbcDEeFIiJLlmOoPpQRSWw")
# flags after which ssh runs no remote command: forwarding only, a control command, a config dump,
# a subsystem
SSH_NO_COMMAND = set("NGVs")
SSH_NAMES = {"ssh", "autossh"}
LAUNCHER = "omnigent_agent.py"
# a tool that builds or tests whatever its arguments, and those that do so by one subcommand
BUILD_TOOLS = {
    "make",
    "gmake",
    "ninja",
    "cmake",
    "bazel",
    "bazelisk",
    "xcodebuild",
    "gradle",
    "gradlew",
    "mvn",
    "mvnw",
    "pytest",
    "py.test",
    "tox",
    "nox",
    "just",
    "cargo",
}
BUILD_SUBCOMMANDS = {
    "npm": {"test", "t", "run", "run-script", "build", "install", "i", "ci", "exec"},
    "pnpm": {"test", "t", "run", "build", "install", "i", "exec"},
    "yarn": {"test", "run", "build", "install"},
    "bun": {"test", "run", "build", "install"},
    "go": {"build", "test", "run", "vet", "generate", "install"},
    "swift": {"build", "test", "run"},
    "dotnet": {"build", "test", "run", "publish"},
    "mise": {"run", "r"},
}
GATE_SCRIPTS = {"approvals.py", "gatekeeper.py"}
GATE_SUBCOMMANDS = {"land", "record", "approve", "delegate", "local-ci", "affected-tests", "heavy"}
# git's global options that take the next word as their value
GIT_VALUED = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
INSTEAD = (
    "Work for a host runs in an agent session on that host, or in a Claude cloud session, so it"
    " stays visible, resumable and on the owner's board (orchestrating-agents' SKILL.md, Rules)."
    " Instead: start a session on that host through orchestrating-agents' Omnigent backend"
    " (`omnigent_agent.py start --host <host> ...`, its report a file) with this command in its"
    " brief, or, when the run needs no particular machine, run it in a Claude cloud session"
    " (`omnigent_agent.py claude-cloud-run -- <command>`). A Mergify `land` and `record verdict`"
    " only call GitHub's API: run them in your own session, wherever it is. Reading a host's state"
    " over ssh (a log, `git status`, `/proc/loadavg`, `ps`) stays allowed."
)


def ssh_remote(words: list[str]) -> tuple[str, str] | None:
    """``(host, remote command)`` of ``ssh [options] <host> <command...>``, the command's words joined
    by spaces as ssh hands them to the remote shell; None when ``words`` is no ssh call or runs no
    remote command (none given, ``-N``, ``-O``, ``-G``, ``-V``, ``-s``)."""
    if not words or Path(words[0]).name not in SSH_NAMES:
        return None
    i = 1
    while i < len(words) and words[i].startswith("-") and words[i] != "-":
        word = words[i]
        i += 1
        if word == "--":
            break
        for j, letter in enumerate(word[1:], 1):
            if letter in SSH_NO_COMMAND:
                return None
            if letter in SSH_VALUED:
                if j == len(word) - 1:
                    i += 1  # the value is the next word; else it is the rest of this one
                break
    if i + 1 >= len(words):
        return None
    return words[i], " ".join(words[i + 1 :])


def launcher_remote(words: list[str]) -> tuple[str, str] | None:
    """``(host, command)`` of ``omnigent_agent.py ssh <host> [--why <purpose>] -- <command...>``, run
    as a script or through ``python3``/``uv run``; one word after ``--`` is a shell command as
    written, several are joined as the launcher joins them. None for any other command."""
    for i, word in enumerate(words):
        if Path(word).name == LAUNCHER:
            break
    else:
        return None
    if words[i + 1 : i + 2] != ["ssh"] or i + 2 >= len(words):
        return None
    host, rest = words[i + 2], words[i + 3 :]
    if "--" not in rest:
        return None
    command = rest[rest.index("--") + 1 :]
    return (host, " ".join(command)) if command else None


def git_push(args: list[str]) -> bool:
    """Whether git's arguments, past its global options, are ``push``."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GIT_VALUED else 1
    return args[i : i + 1] == ["push"]


def remote_heavy(words: list[str]) -> str | None:
    """What one remote segment (its leading words already stripped) does that belongs in a session
    on its host: ``build or test``, ``gate or land`` or ``git push``; None for anything else."""
    words = after_uv_run(words)
    if not words:
        return None
    prog = Path(words[0]).name
    args = words[1:]
    for i, word in enumerate(words):
        if Path(word).name in GATE_SCRIPTS:
            sub = [a for a in words[i + 1 :] if not a.startswith("-")][:1]
            return "gate or land" if sub and sub[0] in GATE_SUBCOMMANDS else None
    if python_m_pytest(words) is not None or prog in BUILD_TOOLS:
        return "build or test"
    if prog in BUILD_SUBCOMMANDS and args[:1] and args[0] in BUILD_SUBCOMMANDS[prog]:
        return "build or test"
    if prog == "mise" and args[:2] == ["tasks", "run"]:
        return "build or test"
    if prog == "git" and git_push(args):
        return "git push"
    return None


def judge_remote(command: str, depth: int = 0) -> str | None:
    """The first thing ``command``, run by a remote shell, does that ``remote_heavy`` names."""
    for words in segments(command):
        rest = strip_leading(words, Path("/"))[0]
        if (inner := shell_string(rest)) is not None:
            if depth < SHELL_DEPTH and (found := judge_remote(inner, depth + 1)):
                return found
            continue
        if found := remote_heavy(rest):
            return found
    return None


def find_remote(command: str, depth: int = 0) -> tuple[str, str, str] | None:
    """``(host, remote command, what it does)`` for the first ssh call in ``command`` whose remote
    command ``judge_remote`` refuses; None when there is none."""
    for words in segments(command):
        rest = strip_leading(words, Path("/"))[0]
        if (inner := shell_string(rest)) is not None:
            if depth < SHELL_DEPTH and (found := find_remote(inner, depth + 1)):
                return found
            continue
        call = ssh_remote(rest) or launcher_remote(rest)
        if call and (what := judge_remote(call[1])):
            return call[0], call[1], what
    return None


def verdict(payload: dict) -> tuple[int, str]:
    """The hook's exit code and stderr text for this tool call: ``(2, <refusal>)`` for a remote run
    that belongs in a session on its host, else ``(0, "")``."""
    if payload.get("tool_name", "Bash") != "Bash":
        return 0, ""
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0, ""
    try:
        found = find_remote(command)
    except ValueError:  # a quote it can't close: allowed, as anything it can't parse
        return 0, ""
    if found is None:
        return 0, ""
    host, remote, what = found
    remote = re.sub(r"\s+", " ", remote).strip()
    return 2, f"Remote run refused: `{remote}` over ssh to {host} is a {what}. {INSTEAD}"


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
