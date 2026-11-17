#!/usr/bin/env python3
"""A Claude Code PreToolUse hook on Bash: refuse a heavy test or check run in a host session, so a
lead's own runs go to a Claude cloud session by default (engineering-loop SKILL.md, Where heavy
steps run).

It reads the tool call's JSON on stdin (``tool_input.command``, ``cwd``) and refuses, with exit 2
and the reason on stderr, only when all of these hold: the session is not a cloud one
(``CLAUDE_CODE_REMOTE`` is not ``true``); the repository holding ``cwd`` has
``docs/agents/loop.md`` without a ``Cloud worker: none`` line; the command does not start with
``LOOP_HOST_RUN=<reason>``, the host fallback; and a segment of it is heavy (``heavy``). The
reason names the ``cloud-run`` call for that exact command and the fallback. Anything it cannot
read or parse is allowed, since a parse bug must never block work; a copy deployed for Codex,
under a ``.codex`` directory, allows everything, since it is written to Claude Code's contract.
Stdlib only, and no subprocess, since it runs before every Bash call.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

HOST_RUN = "LOOP_HOST_RUN"
LOOP_FILE = Path("docs") / "agents" / "loop.md"
HOST_WORKERS = re.compile(r"^Cloud worker:[ \t]*none\b", re.MULTILINE | re.IGNORECASE)
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "{", "}", "\n"}
REDIRECT = re.compile(r"\d*[<>]")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\1[^\n]*\n")
PYTHON = re.compile(r"python(\d+(\.\d+)?)?")
# pytest options whose value is the next argument, so it is not read as a test path
PYTEST_VALUED = {
    "-k", "-m", "-p", "-c", "-o", "-W", "--rootdir", "--confcutdir", "--basetemp",
    "--deselect", "--ignore", "--ignore-glob", "--junitxml", "--log-file", "--tb",
    "--durations", "--maxfail", "--import-mode", "--capture", "--override-ini",
}  # fmt: skip
TIMEOUT_VALUED = {"-s", "--signal", "-k", "--kill-after"}
UV_VALUED = {
    "--with", "--with-requirements", "--with-editable", "--python", "-p", "--project",
    "--directory", "--package", "--extra", "--group", "--env-file", "--index", "--index-url",
}  # fmt: skip


def deployed_for_codex(path: Path) -> bool:
    return ".codex" in path.resolve().parts


def repo_root(cwd: Path) -> Path | None:
    """The checkout holding ``cwd``: the nearest directory with a ``.git`` entry."""
    for folder in (cwd, *cwd.parents):
        if (folder / ".git").exists():
            return folder
    return None


def loop_repo(cwd: Path) -> Path | None:
    """``cwd``'s checkout when it runs the engineering loop with cloud workers: it has loop.md
    and no ``Cloud worker: none`` line in it."""
    root = repo_root(cwd)
    if root is None:
        return None
    try:
        text = (root / LOOP_FILE).read_text()
    except OSError, UnicodeDecodeError:
        return None
    return None if HOST_WORKERS.search(text) else root


def without_heredocs(command: str) -> str:
    """``command`` with each here-document's body taken out, since its lines are data."""
    out, at = [], 0
    for found in HEREDOC.finditer(command):
        if found.start() < at:
            continue
        out.append(command[at : found.end()])
        end = re.compile(rf"^[ \t]*{re.escape(found.group(2))}[ \t]*$", re.MULTILINE)
        close = end.search(command, found.end())
        at = close.end() if close else len(command)
    return "".join(out) + command[at:]


def tokens(command: str) -> list[str]:
    """The shell words and operators of ``command``, a newline among the operators; ``ValueError``
    when it can't be split (an unclosed quote)."""
    lex = shlex.shlex(without_heredocs(command), posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = "#"
    return list(lex)


def segments(words: list[str]) -> list[list[str]]:
    """The simple commands in a word list, split at every operator, redirections dropped."""
    found, current, skip = [], [], False
    for at, word in enumerate(words):
        if skip:
            skip = False
            continue
        if word in SEPARATORS or set(word) <= set(";&|()\n"):
            if current:
                found.append(current)
            current = []
        elif set(word) <= set("<>&") or REDIRECT.fullmatch(word):
            skip = True  # the redirection's target follows
        elif word.isdigit() and at + 1 < len(words) and words[at + 1][:1] in ("<", ">"):
            continue  # a redirection's descriptor, `2` of `2>&1`, which the split cut off
        else:
            current.append(word)
    if current:
        found.append(current)
    return found


def unwrap(argv: list[str]) -> list[list[str]]:
    """The commands ``argv`` runs once its wrappers are peeled: env assignments, ``env``,
    ``timeout``, ``nohup``, ``exec``, ``time``, ``nice``, ``flock``, ``uv run``, ``mise exec``,
    ``python -m``, ``approvals.py heavy``, the detach recipe's ``perl -e`` and ``sh -c``; more
    than one for ``sh -c '<text>' <name> <args>``, whose args the text may run."""
    while argv:
        head = Path(argv[0]).name
        if ASSIGNMENT.match(argv[0]) or head in ("nohup", "exec", "time", "command", "builtin"):
            argv = argv[1:]
        elif head == "env":
            argv = argv[1:]
            while argv and (argv[0].startswith("-") or ASSIGNMENT.match(argv[0])):
                argv = argv[2:] if argv[0] in ("-u", "-C", "--unset", "--chdir") else argv[1:]
        elif head == "nice":
            argv = argv[3:] if argv[1:2] == ["-n"] else argv[1:]
        elif head == "timeout":
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = argv[2:] if argv[0] in TIMEOUT_VALUED else argv[1:]
            argv = argv[1:]  # the duration
        elif head == "flock":
            argv = argv[1:]
            while argv and argv[0].startswith("-"):
                argv = (
                    argv[2:]
                    if argv[0] in ("-w", "--timeout", "-E", "--conflict-exit-code")
                    else argv[1:]
                )
            argv = argv[1:]  # the lock file
            if argv[:1] == ["-c"]:
                return [w for t in argv[1:2] for w in commands(t)]
        elif head in ("sh", "bash", "zsh", "dash") and "-c" in argv[1:]:
            at = argv.index("-c", 1)
            inner = commands(argv[at + 1]) if len(argv) > at + 1 else []
            rest = argv[at + 3 :]  # after the text and its $0: what "$@" in the text runs
            return inner + (unwrap(rest) if rest else [])
        elif head == "perl" and "-e" in argv[1:]:
            at = argv.index("-e", 1)
            argv = argv[at + 2 :]  # the detach recipe: perl -e '...exec @ARGV' <cmd>
        elif head == "uv" and argv[1:2] == ["run"]:
            argv = argv[2:]
            while argv and argv[0].startswith("-"):
                argv = argv[2:] if argv[0] in UV_VALUED else argv[1:]
        elif head == "mise" and argv[1:2] in (["exec"], ["x"]):
            argv = argv[argv.index("--") + 1 :] if "--" in argv else []
        elif (
            PYTHON.fullmatch(head)
            and "-m" in argv[1:]
            and all(a.startswith("-") for a in argv[1 : argv.index("-m", 1)])
        ):
            argv = argv[argv.index("-m", 1) + 1 :]
        elif PYTHON.fullmatch(head) and len(argv) > 1 and not argv[1].startswith("-"):
            argv = argv[1:]  # python3 <script> ...: the script is the command
        elif head == "approvals.py" and argv[1:2] == ["heavy"]:
            argv = argv[2:]
        else:
            return [argv]
    return []


def commands(command: str) -> list[list[str]]:
    """Every simple command ``command`` runs, its wrappers peeled (``unwrap``)."""
    return [argv for segment in segments(tokens(command)) for argv in unwrap(segment)]


def light_pytest(args: list[str]) -> bool:
    """Whether pytest's ``args`` name only test files or node ids, at least one, with no ``-n``."""
    named, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif (
            arg == "--numprocesses"
            or arg.startswith("--numprocesses=")
            or arg.startswith("-n")
            and not arg.startswith("--")
        ):
            return False
        elif arg in PYTEST_VALUED:
            skip = True
        elif not arg.startswith("-"):
            named.append(arg)
    return bool(named) and all("::" in a or a.endswith(".py") for a in named)


def positionals(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith(("-", "+"))]


def mise_tasks(args: list[str]) -> list[str]:
    """The task names of ``mise run``'s arguments: the first word, and each after ``:::``."""
    found, take, skip = [], True, False
    for arg in args:
        if skip:
            skip = False
        elif arg == ":::":
            take = True
        elif take and arg in ("-j", "--jobs", "-C", "--cd", "-E", "--env", "-o", "--output"):
            skip = True
        elif take and not arg.startswith("-"):
            found.append(arg)
            take = False
    return found


def heavy(argv: list[str]) -> bool:
    """Whether one unwrapped command is a heavy test or check run (spec #1233's list)."""
    if not argv:
        return False
    name, args = Path(argv[0]).name, argv[1:]
    words = positionals(args)
    if name in ("pytest", "py.test"):
        return not light_pytest(args)
    if name == "mise" and args[:1] in (["run"], ["r"]):
        return any(t.startswith(("check", "test")) for t in mise_tasks(args[1:]))
    if name in ("make", "gmake"):
        return bool({"check", "test"} & set(words))
    if name in ("npm", "pnpm", "yarn"):
        first = words[:2]
        return first[:1] in (["test"], ["t"]) or first in (["run", "test"], ["run-script", "test"])
    if name == "cargo":
        return words[:1] == ["test"]
    if name == "go":
        return words[:1] == ["test"]
    if name in ("tox", "nox"):
        return True
    if name in ("gradle", "gradlew"):
        return any(w.rsplit(":", 1)[-1] in ("test", "check", "build") for w in words)
    if name in ("mvn", "mvnw"):
        return any(w.rsplit(":", 1)[-1] in ("test", "verify") for w in words)
    if name == "approvals.py":
        if words[:1] == ["local-ci"]:
            return any(
                a == f"--{f}" or a.startswith(f"--{f}=") for a in args for f in ("run", "record")
            )
        return words[:1] == ["affected-tests"]
    return False


def launcher(hook: Path) -> str:
    """omnigent_agent.py where the pack put it beside this hook, else its skill-relative name."""
    tail = Path("skills") / "orchestrating-agents" / "scripts" / "omnigent_agent.py"
    here = hook.resolve()
    # deployed: <root>/.claude/hooks/<package>/hooks/host_run.py; in the pack: <pack>/hooks/host_run.py
    for base in (here.parents[3] if len(here.parents) > 3 else None, here.parents[1]):
        if base and (base / tail).is_file():
            return str(base / tail)
    return "<orchestrating-agents>/scripts/omnigent_agent.py"


def refusal(command: str, segment: list[str], cwd: Path, hook: Path) -> str:
    return (
        f"Refused on this host: `{shlex.join(segment)}` is a heavy run, and a heavy run goes to a"
        " Claude cloud session (engineering-loop SKILL.md, Where heavy steps run). Run it there:\n"
        f"  python3 {shlex.quote(launcher(hook))} cloud-run --checkout {shlex.quote(str(cwd))}"
        f" -- {shlex.quote(command)}\n"
        "It exits with the command's code and prints the report path. Only when the cloud route"
        " failed (cloud-run exits 125 and says why) or the run needs this host (a device, a `host`"
        f" gate step), run it here and say so in your report:\n  {HOST_RUN}=<reason> {command}"
    )


def verdict(data: dict, env: dict[str, str], hook: Path) -> str | None:
    """The refusal for the tool call ``data``, else None (allowed)."""
    if env.get("CLAUDE_CODE_REMOTE") == "true" or deployed_for_codex(hook):
        return None
    command = (data.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    if re.match(rf"\s*{HOST_RUN}=\S", command):
        return None
    cwd = Path(data.get("cwd") or os.getcwd())
    if loop_repo(cwd) is None:
        return None
    try:
        run = commands(command)
    except ValueError, IndexError:
        return None  # can't parse it: allowed
    for argv in run:
        if heavy(argv):
            return refusal(command.strip(), argv, cwd, hook)
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        reason = verdict(data, dict(os.environ), Path(__file__)) if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001  (a hook bug never blocks work)
        return 0
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
