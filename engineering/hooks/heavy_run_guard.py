#!/usr/bin/env python3
"""A Claude Code PreToolUse hook on Bash: refuse a heavy test or check run on a host (#1233).

engineering-loop's SKILL.md, Where heavy steps run, sends a lead's own suite, build and check runs
to a Claude cloud session; this hook makes that the default. It reads the tool call's JSON on
stdin and refuses (exit 2, the reason on stderr, as Claude Code's PreToolUse contract takes it) a
command one of whose segments is heavy (``heavy``), when all of these hold:

- the session is not a cloud one (``CLAUDE_CODE_REMOTE`` is not ``true``);
- the call's ``cwd`` is inside a repository with ``docs/agents/loop.md``, whose ``Cloud worker:``
  line is not ``none`` (a project that keeps its workers on hosts runs there);
- the segment is not prefixed ``LOOP_HOST_RUN=<reason>`` (nor the whole command), the host
  fallback: the cloud route failed, or the run needs this host.

The refusal names the ``cloud-run`` call for that exact command and the fallback. Anything it
can't read or parse is allowed (exit 0), so a bug here never blocks work. Stdlib only, no
subprocess: it runs on every Bash call.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

LOOP_FILE = Path("docs") / "agents" / "loop.md"
NO_CLOUD = re.compile(r"^Cloud worker:[ \t]*none\b", re.MULTILINE | re.IGNORECASE)
HOST_RUN = "LOOP_HOST_RUN"
ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = {"&&", "||", ";", "|", "&", "|&", ";;", "(", ")", "\n"}
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\1")
# the leading words a segment's real command follows (as the issue lists them)
PREFIXES = {"nohup", "exec"}
# pytest options that take the next word as their value, so it is no test path
PYTEST_VALUED = {
    "-k",
    "-m",
    "-p",
    "-c",
    "-o",
    "-W",
    "-r",
    "--deselect",
    "--ignore",
    "--ignore-glob",
    "--rootdir",
    "--confcutdir",
    "--basetemp",
    "--junitxml",
    "--junit-xml",
    "--maxfail",
    "--durations",
    "--tb",
    "--log-level",
    "--override-ini",
    "--import-mode",
    "--cov",
    "--cov-report",
}
UV_VALUED = {
    "--with",
    "--with-editable",
    "--with-requirements",
    "--project",
    "--directory",
    "--python",
    "-p",
    "--extra",
    "--group",
    "--env-file",
    "--package",
    "--index",
}
TIMEOUT_VALUED = {"-s", "--signal", "-k", "--kill-after"}
LAUNCHER = Path("skills") / "orchestrating-agents" / "scripts" / "omnigent_agent.py"


def repo_root(cwd: Path) -> Path | None:
    """The nearest directory at or above ``cwd`` holding ``.git`` (a checkout or a worktree)."""
    for path in (cwd, *cwd.parents):
        if (path / ".git").exists():
            return path
    return None


def loop_repo(cwd: Path) -> Path | None:
    """The repository root when it runs the loop with cloud workers: it has ``docs/agents/loop.md``
    and no ``Cloud worker: none`` line there; else None."""
    root = repo_root(cwd)
    if root is None:
        return None
    try:
        text = (root / LOOP_FILE).read_text(errors="replace")
    except OSError:
        return None
    return None if NO_CLOUD.search(text) else root


def drop_heredocs(command: str) -> str:
    """``command`` without its here-documents' bodies, which are data, not commands."""
    out: list[str] = []
    ending: str | None = None
    for line in command.split("\n"):
        if ending is not None:
            if line.strip() == ending:
                ending = None
            continue
        out.append(line)
        if found := HEREDOC.search(line.replace("<<<", "   ")):
            ending = found.group(2)
    return "\n".join(out)


def segments(command: str) -> list[list[str]]:
    """The words of each simple command in ``command``, split at ``&&``, ``||``, ``;``, ``|``,
    ``&``, a newline and parentheses. Raises ValueError on a quote it can't close."""
    lex = shlex.shlex(drop_heredocs(command), posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = "#"
    parts: list[list[str]] = [[]]
    target = False  # the next word is a redirection's file, no argument
    for token in lex:
        if token in SEPARATORS or (token and set(token) <= set(";&|\n")):
            parts.append([])
            target = False
        elif token and set(token) <= set("<>&") and set(token) & set("<>"):
            if parts[-1] and parts[-1][-1].isdigit():  # the 2 of 2>file
                parts[-1].pop()
            target = True
        elif target:  # the file, or the 1 of 2>&1
            target = False
        else:
            parts[-1].append(token)
    return [p for p in parts if p]


def strip_leading(words: list[str]) -> tuple[list[str], bool]:
    """The words after a segment's leading ``cd <dir>``, env assignments, ``timeout`` (with its
    options and duration), ``nohup`` and ``exec``, and whether a ``LOOP_HOST_RUN=<reason>``
    assignment was among them."""
    host = False
    i = 0
    while i < len(words):
        word = words[i]
        if ASSIGNMENT.match(word):
            name, _, value = word.partition("=")
            host |= name == HOST_RUN and bool(value.strip())
            i += 1
        elif word == "cd":
            i += 2
        elif word in PREFIXES:
            i += 1
        elif word == "timeout":
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in TIMEOUT_VALUED else 1
            i += 1  # the duration
        else:
            break
    return words[i:], host


def is_test_path(word: str) -> bool:
    """Whether ``word`` names one test file or a node id in one (``path.py::Test::test``)."""
    return word.split("::", 1)[0].endswith(".py")


def heavy_pytest(args: list[str]) -> bool:
    """A pytest run is heavy unless every argument names a test file or node id (options aside)
    and there is no ``-n`` (xdist), which only a suite needs."""
    paths: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        if word == "-n" or word.startswith("--numprocesses") or re.fullmatch(r"-n\S+", word):
            return True
        if word in PYTEST_VALUED:
            i += 2
            continue
        if not word.startswith("-"):
            paths.append(word)
        i += 1
    return not paths or not all(is_test_path(p) for p in paths)


def python_m_pytest(words: list[str]) -> list[str] | None:
    """The pytest arguments of ``python[3[.x]] -m pytest ...``, else None."""
    python = bool(words) and re.fullmatch(r"python(\d+(\.\d+)?)?", Path(words[0]).name)
    return words[3:] if python and words[1:3] == ["-m", "pytest"] else None


def after_uv_run(words: list[str]) -> list[str]:
    """The command ``uv run [options] <cmd>`` runs, else ``words`` unchanged."""
    if len(words) < 2 or Path(words[0]).name != "uv" or words[1] != "run":
        return words
    i = 2
    while i < len(words) and words[i].startswith("-"):
        if words[i] == "--":
            i += 1
            break
        i += 2 if words[i] in UV_VALUED else 1
    return words[i:]


def heavy(words: list[str]) -> bool:
    """Whether one segment's command (its leading words already stripped) is a heavy run."""
    words = after_uv_run(words)
    if not words:
        return False
    prog = Path(words[0]).name
    args = words[1:]
    if (pytest_args := python_m_pytest(words)) is not None:
        return heavy_pytest(pytest_args)
    if prog == "pytest" or prog == "py.test":
        return heavy_pytest(args)
    if prog == "mise" and args[:1] == ["run"]:
        tasks = [a for a in args[1:] if not a.startswith("-")]
        return any(t.startswith(("check", "test")) for t in tasks)
    if prog == "make":
        return any(a in ("check", "test") for a in args)
    if prog in ("npm", "pnpm", "yarn"):
        rest = args[1:] if args[:1] == ["run"] else args
        return rest[:1] == ["test"]
    if prog in ("cargo", "go"):
        return args[:1] == ["test"]
    if prog in ("tox", "nox"):
        return True
    if prog in ("gradle", "gradlew"):
        return any(a in ("test", "check", "build") for a in args)
    if prog in ("mvn", "mvnw"):
        return any(a in ("test", "verify") for a in args)
    for i, word in enumerate(words):
        if Path(word).name == "approvals.py":
            sub = words[i + 1 : i + 2]
            rest = words[i + 2 :]
            if sub == ["affected-tests"]:
                return True
            return sub == ["local-ci"] and any(a in ("--run", "--record") for a in rest)
    return False


def launcher(root: Path) -> str:
    """Where orchestrating-agents' launcher is for this repository: the consumer's deployed skill,
    this pack's own copy beside the hook, else a placeholder naming it."""
    here = Path(__file__).resolve().parent
    for path in (
        root / ".claude" / LAUNCHER,
        root / ".agents" / LAUNCHER,
        root / "engineering" / LAUNCHER,
        here.parent / LAUNCHER,
    ):
        if path.is_file():
            return str(path)
    return "<orchestrating-agents>/scripts/omnigent_agent.py"


def refusal(command: str, cwd: Path, root: Path) -> str:
    """The reason the hook prints: the ``cloud-run`` call for this exact command, and the fallback."""
    run = command.strip()
    if cwd != root:  # the cloud session runs at the checkout's root
        run = f"cd {shlex.quote(os.path.relpath(cwd, root))} && {run}"
    call = (
        f"python3 {shlex.quote(launcher(root))} cloud-run --checkout {shlex.quote(str(root))}"
        f" -- {shlex.quote(run)}"
    )
    return (
        "Heavy run refused on this host: engineering-loop's SKILL.md, Where heavy steps run, sends"
        " a test or check run to a Claude cloud session. Run it there (commit and push first; it"
        " exits with the command's own code):\n"
        f"  {call}\n"
        f"If cloud-run fails, or the run needs this host (a device, a `host` gate step), run it with"
        f" the reason as a prefix: {HOST_RUN}=<reason> {command.strip()}"
    )


def verdict(payload: dict, env: dict[str, str]) -> str | None:
    """The refusal for this tool call, or None to allow it."""
    if env.get("CLAUDE_CODE_REMOTE") == "true":
        return None
    if payload.get("tool_name", "Bash") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    cwd = Path(payload.get("cwd") or os.getcwd())
    root = loop_repo(cwd)
    if root is None:
        return None
    parts = segments(command)
    if parts and parts[0][0].startswith(HOST_RUN + "=") and parts[0][0].partition("=")[2].strip():
        return None  # the whole command starts with the fallback prefix
    for words in parts:
        rest, host = strip_leading(words)
        if not host and heavy(rest):
            return refusal(command, cwd, root)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        reason = verdict(payload, dict(os.environ)) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001  (a parse bug must never block a command)
        return 0
    if reason is None:
        return 0
    print(reason, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
