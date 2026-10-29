#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Mutation check (engineering-loop): undo one production change at a time and see whether a test notices.

    uv run scripts/mutate.py --test '<command>' --log <path> <patch>...

Each patch undoes one change (verifier.md, Mutation-check the new tests, says how to write one). On a clean checkout
it applies each patch alone with `git apply`, runs the test command through the shell, records its exit code, undoes
the patch with `git apply -R` and checks the tree is clean again before the next one. A test command that fails has
killed the patch; one that passes means no test covers that change, and the patch survived.

It refuses a tracked change or an untracked file that isn't ignored, the check `approvals.py local-ci` makes, so
patches under a gitignored `tmp/loop/` don't count, and it refuses any patch that doesn't apply before running a test.
On SIGINT or SIGTERM it stops the test command, undoes the applied patch and then dies of that signal, so a killed run
leaves no mutation in the tree. It takes no lock: a test command that needs the host's heavy slot carries the
project's wrapper itself.

The log: line 1 is `git rev-parse HEAD`, line 2 this command line, then `<patch>: exit <n> killed|survived` per
patch, then each patch's test output under a `== <patch> ==` header. It is rewritten after every patch, so a stopped
run keeps what it finished. Exit 0 when every patch was killed, 1 when one survived (the log names it), 2 when it
refuses, a patch doesn't apply, or the tree can't be restored (stderr names the paths). Standard library and git.
"""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path


class Interrupted(Exception):
    def __init__(self, signum: int) -> None:
        self.signum = signum


class Refused(Exception):
    pass


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def changes() -> str:
    """Every change in the checkout, empty when it is clean (approvals.py's `checkout_state`)."""
    # untracked files and submodule edits listed whatever status.showUntrackedFiles or submodule.*.ignore say
    status = git(
        "status", "--porcelain", "--untracked-files=all", "--ignore-submodules=none"
    ).stdout
    # status skips files whose index flag says so (assume-unchanged, set by core.ignoreStat; skip-worktree)
    hidden = [
        f"{line[2:]} (index flag hides its changes)\n"
        for line in git("ls-files", "-v").stdout.splitlines()
        if line[:1].islower() or line[:1] == "S"
    ]
    return status + "".join(hidden)


def on_signal(signum: int, _frame: object) -> None:
    # a second signal while the patch is undone would leave it half applied
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise Interrupted(signum)


def run_test(command: str) -> tuple[int, str]:
    """The test command's exit code and output; on a signal its whole process group is stopped first."""
    # its own session, so stopping it reaches every process the shell started
    proc = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
        # a .pyc written in the same second as its source hides the next same-sized patch of it
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    try:
        output, _ = proc.communicate()
    except Interrupted:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        raise
    return proc.returncode, output


def restore(top: Path, patch: Path) -> None:
    """Undo `patch` when the tree shows it, then require a clean tree."""
    if changes():
        git("apply", "-R", str(patch), cwd=top)
    left = changes()
    if left:
        raise Refused(f"the tree could not be restored after {patch}:\n{left}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--test", required=True, help="the test command, run through the shell")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("patches", nargs="+", type=Path)
    args = parser.parse_args(argv)
    head = git("rev-parse", "HEAD")
    if head.returncode:
        print(f"mutate: not in a git checkout: {head.stderr.strip()}", file=sys.stderr)
        return 2
    top = Path(git("rev-parse", "--show-toplevel").stdout.strip())
    # git apply run in a subdirectory skips paths outside it, so every apply runs at the top
    patches = [(name, name.resolve()) for name in args.patches]
    lines = [head.stdout.strip(), shlex.join(sys.argv)]
    outputs: list[str] = []

    def write_log() -> None:
        args.log.write_text("\n".join(lines + outputs) + "\n")

    write_log()
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    survived = False
    current: Path | None = None
    try:
        dirty = changes()
        if dirty:
            raise Refused(
                f"the tree has changes, so a restore could not tell them from a patch:\n{dirty}"
            )
        for name, path in patches:
            check = git("apply", "--check", str(path), cwd=top)
            if check.returncode:
                raise Refused(f"{name} does not apply: {check.stderr.strip()}")
        for name, path in patches:
            current = path
            applied = git("apply", str(path), cwd=top)
            if applied.returncode:
                raise Refused(f"{name} does not apply: {applied.stderr.strip()}")
            code, output = run_test(args.test)
            restore(top, path)
            current = None
            survived |= code == 0
            lines.append(f"{name}: exit {code} {'survived' if code == 0 else 'killed'}")
            outputs += ["", f"== {name} ==", output.rstrip("\n")]
            write_log()
    except Interrupted as stop:
        if current:
            restore(top, current)
        lines.append(f"stopped by {signal.Signals(stop.signum).name}")
        write_log()
        signal.signal(stop.signum, signal.SIG_DFL)
        os.kill(os.getpid(), stop.signum)
        return 128 + stop.signum
    except Refused as refusal:
        # nothing is applied here: git apply is all or nothing, and a failed restore names what it left
        lines.append(f"refused: {str(refusal).splitlines()[0]}")
        write_log()
        print(f"mutate: {refusal}", file=sys.stderr)
        return 2
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
