#!/usr/bin/env python3
"""A Claude Code PreToolUse hook on Bash: refuse a command that prints the whole environment or a
secret variable's value (#2359).

A session's tool output lands in a transcript the agent server stores and shows in its UI, so a
secret printed there leaves the VM. A cloud environment carries secrets by design (the Codex login
`cloud_verifier.py seed` stores as ``CODEX_AUTH_JSON``, a Claude Code token, tokens a project adds),
and nothing redacts a transcript after the fact: this is the check in code. It reads the tool
call's JSON on stdin and refuses (exit 2, the reason on stderr, as Claude Code's PreToolUse
contract takes it) a command one of whose segments:

- prints the whole environment: ``env``, ``printenv``, ``set``, ``export``/``export -p``,
  ``declare -p``/``-x``, ``typeset``, ``compgen -e`` is not one (it lists names only), or reads
  ``/proc/<pid>/environ``; or an interpreter one-liner (``python -c``, ``node -e``, ...) that
  prints ``os.environ`` or ``process.env`` whole;
- prints a variable whose name looks like a secret (``*_TOKEN``, ``*_KEY``, ``*_SECRET``,
  ``*AUTH*``, ``*PASSWORD*``, ``*CREDENTIAL*``): ``printenv NAME``, ``echo "$NAME"``, ``printf``,
  ``declare -p NAME``, or an interpreter one-liner that prints it.

Output that goes into a hasher or a counter (``| wc -c``, ``| sha256sum``, ``| grep -q``), a
variable's length (``${#NAME}``), a test (``[ -n "$NAME" ]``), ``env FOO=1 cmd``, ``printenv HOME``
and every command that merely has the variable in its environment pass. The refusal says why and
how to check a variable without printing it. Anything it can't read or parse is allowed (exit 0),
so a bug here never blocks work. Stdlib only, no subprocess: it runs on every Bash call.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from heavy_run_guard import (
    SEPARATORS,
    SHELL_DEPTH,
    drop_heredocs,
    shell_string,
    strip_leading,
)

# a name that holds a secret: AUTHOR (git's) and SSH_AUTH_SOCK (a socket path) do not
SECRET_NAME = re.compile(
    r"^[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH(?!OR|_SOCK)|APIKEY|API_KEY|PRIVATE_KEY|_KEY$)"
    r"[A-Z0-9_]*$|^KEY$"
)
# a command that reduces its input to a length or a digest, or only tests it: no value comes out
REDUCERS = {"wc", "sha1sum", "sha224sum", "sha256sum", "sha384sum", "sha512sum", "shasum", "md5sum"}
REDUCERS |= {"cksum", "b3sum"}
QUIET_GREP = {"-q", "-c", "--quiet", "--silent", "--count", "-l", "-L"}
PRINTERS = {"echo", "printf", "print"}
SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "find", "ls", "stat", "test", "["}
INTERPRETERS = re.compile(r"^(python[\d.]*|node|nodejs|deno|bun|perl|ruby|php|lua)$")
CODE_FLAGS = {"-c", "-e", "-p", "-r", "--eval", "--print", "-E"}
ENV_RUN = re.compile(r"/proc/[^/\s'\"]+/environ\b")
ENV_REDIRECT = re.compile(r"<\s*['\"]?/proc/[^/\s'\"]+/environ\b")
# the whole environment inside code: os.environ / process.env / ENV / %ENV not indexed or looked up
CODE_WHOLE = re.compile(
    r"\bos\.environ\b(?!\s*(?:\[|\.get\b|\.setdefault\b|\.pop\b))"
    r"|\bprocess\.env\b(?![\w.\[])"
    r"|\b(?:Deno\.env\.toObject|environ\.items|getenv\(\s*\))"
    r"|(?<![\w$])%ENV\b|\bENV\.(?:to_h|each|inspect|to_a|map)\b|\bENV(?![\w\[.])|\$_ENV\b|\$_SERVER\b|\bgetenv\(\)"
)
CODE_NAMED = re.compile(r"(?:environ|getenv|process\.env|ENV|env\.get)\W{1,4}([A-Za-z0-9_]+)")
CODE_PRINTS = re.compile(r"print|console\.|echo|puts|write|say\b|dump|stringify|log\b|inspect")
VAR_USE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?|\$\{!?([A-Za-z_][A-Za-z0-9_]*)")

HOW = (
    "Check a variable without printing it: `printenv NAME | wc -c` (its length), `printenv NAME |"
    ' sha256sum | cut -c1-8` (a short hash), `[ -n "${NAME-}" ] && echo set`, or list the names'
    " only with `compgen -e`. A transcript is stored by the agent server and shown in its UI, so a"
    " value printed there is no longer secret."
)


def secret(name: str) -> bool:
    return bool(SECRET_NAME.match(name))


def pipelines(command: str) -> list[tuple[list[str], str]]:
    """Each simple command's words with the separator that follows it ("" at the end), split as
    ``heavy_run_guard.segments`` splits them. Raises ValueError on a quote it can't close."""
    lex = shlex.shlex(drop_heredocs(command), posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = "#"
    parts: list[list[str]] = [[]]
    seps: list[str] = []
    target = False
    for token in lex:
        if token in SEPARATORS or (token and set(token) <= set(";&|\n")):
            seps.append(token)
            parts.append([])
            target = False
        elif token and set(token) <= set("<>&") and set(token) & set("<>"):
            if parts[-1] and parts[-1][-1].isdigit():
                parts[-1].pop()
            target = True
        elif target:
            target = False
        else:
            parts[-1].append(token)
    seps.append("")
    return [(p, s) for p, s in zip(parts, seps) if p]


def reduces(words: list[str]) -> bool:
    """Whether a command turns its input into a length, a digest or an exit status."""
    rest, _, _ = strip_leading(words, None)
    if not rest:
        return False
    prog, args = Path(rest[0]).name, rest[1:]
    if prog in REDUCERS:
        return True
    if prog in ("grep", "egrep", "fgrep", "rg"):
        return any(a in QUIET_GREP or re.fullmatch(r"-[a-zA-Z]*[qc][a-zA-Z]*", a) for a in args)
    if prog == "openssl":
        return args[:1] == ["dgst"]
    return False


def names_used(words: list[str]) -> list[str]:
    """The secret-shaped variables a command line reads with ``$NAME`` or ``${NAME}``, never
    ``${#NAME}`` (a length)."""
    found: list[str] = []
    for word in words:
        for m in VAR_USE.finditer(word):
            name = m.group(1) or m.group(2)
            if name and secret(name):
                found.append(name)
    return found


def judge_words(rest: list[str], reduced: bool) -> str | None:
    """The refusal for one command (its leading words stripped), else None. ``reduced``: its output
    goes into a hasher or counter."""
    prog, args = Path(rest[0]).name, rest[1:]
    plain = [a for a in args if not a.startswith("-")]
    flags = "".join(a[1:] for a in args if re.fullmatch(r"-[A-Za-z]+", a))
    if ENV_RUN.search(" ".join(args)) and prog not in SEARCHERS and not reduced:
        return "it reads a process's whole environment (/proc/<pid>/environ)"
    if prog == "printenv":
        if reduced:
            return None
        named = [a for a in plain]
        if not named:
            return "`printenv` with no variable named prints the whole environment"
        if bad := [n for n in named if secret(n)]:
            return f"`printenv {bad[0]}` prints a secret's value"
        return None
    if prog in ("set",) and not args:
        return None if reduced else "`set` with no argument prints every variable and function"
    if prog == "export" and (not args or "p" in flags and not plain):
        return None if reduced else "`export -p` prints every exported variable"
    if prog in ("declare", "typeset"):
        dump = not plain and ("p" in flags or "x" in flags or not args)
        if dump:
            return None if reduced else f"`{prog}` with no variable named prints every variable"
        if "p" in flags and (bad := [n for n in plain if secret(n)]) and not reduced:
            return f"`{prog} -p {bad[0]}` prints a secret's value"
    if prog == "env" and not plain and not any("=" in a for a in args):
        return None if reduced else "`env` with no command prints the whole environment"
    if prog in PRINTERS and not reduced and (bad := names_used(args)):
        return f"`{prog}` prints ${bad[0]}, which looks like a secret"
    if INTERPRETERS.match(prog) and not reduced:
        for i, a in enumerate(args):
            if a in CODE_FLAGS or re.fullmatch(r"-[a-zA-Z]*[ceE]", a):
                code = " ".join(args[i + 1 :])
                if CODE_PRINTS.search(code):
                    if CODE_WHOLE.search(code):
                        return f"`{prog}` code prints the whole environment"
                    if any(secret(n) for n in CODE_NAMED.findall(code)):
                        return f"`{prog}` code prints a variable that looks like a secret"
                break
    return None


def judge(command: str, depth: int = 0) -> str | None:
    """The reason ``command`` is refused, else None."""
    if ENV_REDIRECT.search(command):
        return "it reads a process's whole environment (/proc/<pid>/environ)"
    items = pipelines(command)
    for i, (words, sep) in enumerate(items):
        # a segment whose output a later segment of its pipeline reduces to a length or a digest
        j, reduced = i, False
        while j < len(items) and items[j][1] in ("|", "|&"):
            j += 1
            reduced = reduced or reduces(items[j][0])
        rest, _, _ = strip_leading(words, None)
        prefix = words[: len(words) - len(rest)]
        if not rest:
            if any(Path(w).name == "env" for w in prefix) and not reduced:
                return "`env` with no command prints the whole environment"
            continue
        if (inner := shell_string(rest)) is not None:
            if depth < SHELL_DEPTH and (why := judge(inner, depth + 1)):
                return why
            continue
        if why := judge_words(rest, reduced):
            return why
    return None


def verdict(payload: dict) -> tuple[int, str]:
    """The hook's exit code and its stderr line for one tool call."""
    if payload.get("tool_name") not in (None, "Bash"):
        return 0, ""
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return 0, ""
    why = judge(command)
    if why is None:
        return 0, ""
    return 2, f"secret_env_guard: refused, {why}. {HOW}"


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
