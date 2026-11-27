#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Acceptance checks (engineering-loop): run one spec's checks from a folder of executables.

    uv run scripts/acceptance.py <issue>
    uv run scripts/acceptance.py --all

The fallback for a project whose `docs/agents/loop.md` has no `Acceptance tests: <command>` line
(SKILL.md, Acceptance checks). It runs every executable file in `acceptance/<issue>/` at the repo
root (the top of the git checkout it is run in, else the current directory), in name order, each
from the repo root with no input: a shell script, a SQL client call, an HTTP call, any language,
since the runner reads only each file's exit code. A non-executable file (a fixture, a README) and
a subfolder are not checks and are skipped. Each check's own output passes through, then one line:

    PASS acceptance/7/01-ok.sh (0.1s)
    FAIL acceptance/7/02-broken.sh (2.3s)

A check whose first lines say `# acceptance: live` needs a live environment (a cloud session, a server), and one that
says `# acceptance: skip <issue link>` is known red with its issue linked; `--all` skips either with a
`SKIP` line naming the reason; run by its issue number it runs as any other.

A file that cannot be started (no shebang, say) is a FAIL with the reason. `--all` runs every
`acceptance/*/` folder in issue order, for the nightly. The last line is the total:
`TOTAL <n> checks, <p> passed, <k> skipped, <f> failed (<s>s)`: `<n>` is every check found, so the three parts add up
(a `skip` marker with no issue linked is not honoured: that check runs, after a `NOTE` line saying so).

The budget: one spec's run should finish within 10 min and the `--all` run within 90 min, or the
minutes loop.md sets with `Acceptance budget: <spec minutes>, <nightly minutes>`. Over it, one more
line says so (`OVER BUDGET ...`) and the exit code is still the checks' own, since the budget is a
signal to split a slow check or move it to the nightly, not a gate. A malformed budget line is
reported and the defaults apply.

Exit codes: 0 every check passed; 1 a check failed; 2 nothing to run (the folder is missing or holds
no executable file, or under `--all` no folder does, or one folder holds none and nothing failed),
so "no checks" is never read as "passed"; a usage error also exits 2.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
import time
from pathlib import Path

FOLDER = "acceptance"
LOOP_MD = Path("docs") / "agents" / "loop.md"
DEFAULT_BUDGET = (10.0, 90.0)  # minutes: one spec's run, the --all run


def repo_root() -> Path:
    """The top of the git checkout the command runs in, else the current directory."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return Path.cwd()
    return Path(out) if out else Path.cwd()


def gatekeeper() -> object:
    """gatekeeper.py beside this script, loaded by path: its `loop_setting` is the one reader of loop.md's values."""
    spec = importlib.util.spec_from_file_location(
        "acceptance_gatekeeper", Path(__file__).resolve().with_name("gatekeeper.py")
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # its dataclasses look themselves up there
    spec.loader.exec_module(module)
    return module


def budget(root: Path) -> tuple[float, float]:
    """The (spec, nightly) minutes loop.md sets with `acceptance.budget` in its `## Loop settings` block, or with the
    line `Acceptance budget:`, else the defaults. A malformed line is reported and the defaults apply; a block off its
    schema stops the run, naming the key."""
    path = root / LOOP_MD
    if not path.is_file():
        return DEFAULT_BUDGET
    text = path.read_text(errors="replace")
    gk = gatekeeper()
    try:
        found = gk.loop_setting(text, "acceptance.budget")  # type: ignore[attr-defined]
    except gk.Refused as e:  # type: ignore[attr-defined]
        if gk.LOOP_HEAD.search(text):  # type: ignore[attr-defined]
            sys.exit(f"acceptance: {LOOP_MD}: {e}")
        print(f"acceptance: {LOOP_MD}: {e}; using 10, 90", file=sys.stderr)
        return DEFAULT_BUDGET
    return DEFAULT_BUDGET if found is None else found


def checks(folder: Path) -> list[Path]:
    """Every executable regular file directly in `folder`, in name order."""
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and os.access(p, os.X_OK)),
        key=lambda p: p.name,
    )


MARKER = re.compile(r"^#\s*acceptance:\s*(live|skip)\b[ \t]*(\S*)", re.IGNORECASE | re.MULTILINE)


def skipped(check: Path) -> str | None:
    """Why `--all` skips `check`, from the marker in its first lines, else None. `# acceptance: live`: it needs a live
    environment (a cloud session, a server) that a scheduled run has not. `# acceptance: skip <issue link>`: it is
    known red and its issue is linked (a known-red check is skipped with its issue, never removed). Run by its issue
    number, a marked check runs as any other."""
    try:
        found = MARKER.search(check.read_text(errors="replace")[:1000])
    except OSError:
        return None
    if not found:
        return None
    if found[1].lower() == "live":
        return "needs a live environment"
    # a `skip` with no issue linked is not honoured: the check runs, so a known-red check is never hidden
    return f"known red, tracked in {found[2]}" if found[2] else None


def unlinked(check: Path) -> bool:
    """Whether `check` carries `# acceptance: skip` with no issue linked: the marker is ignored and the check runs."""
    try:
        found = MARKER.search(check.read_text(errors="replace")[:1000])
    except OSError:
        return False
    return bool(found) and found[1].lower() == "skip" and not found[2]


def issue_order(folder: Path) -> tuple[int, int, str]:
    """Numbered folders first, by number, then any other by name."""
    name = folder.name
    return (0, int(name), name) if name.isdigit() else (1, 0, name)


def run(check: Path, root: Path) -> bool:
    """Run one check from the repo root and print its PASS or FAIL line."""
    shown = check.relative_to(root).as_posix()
    sys.stdout.flush()
    started = time.monotonic()
    try:
        code = subprocess.run(
            [str(check)], cwd=root, stdin=subprocess.DEVNULL, check=False
        ).returncode
        reason = "" if code == 0 else f", exit {code}"
    except OSError as error:
        code, reason = -1, f", not started: {error.strerror or error}"
    seconds = time.monotonic() - started
    print(f"{'PASS' if code == 0 else 'FAIL'} {shown} ({seconds:.1f}s{reason})", flush=True)
    return code == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a spec's acceptance checks: every executable in acceptance/<issue>/."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("issue", nargs="?", help="the spec's issue number")
    target.add_argument("--all", action="store_true", help="every acceptance/*/ folder")
    args = parser.parse_args(argv)

    root = repo_root()
    base = root / FOLDER
    if args.all:
        folders = (
            sorted((p for p in base.iterdir() if p.is_dir()), key=issue_order)
            if base.is_dir()
            else []
        )
        if not folders:
            print(
                f"acceptance: no folder under {FOLDER}/, so there is nothing to run",
                file=sys.stderr,
            )
            return 2
    else:
        issue = args.issue.lstrip("#")
        if not issue.isdigit():
            parser.error(f"the issue is a number, not {args.issue!r}")
        folders = [base / issue]
        if not folders[0].is_dir():
            print(
                f"acceptance: {FOLDER}/{issue}/ does not exist, so there is nothing to run",
                file=sys.stderr,
            )
            return 2

    started = time.monotonic()
    passed = failed = skips = 0
    empty = []
    for folder in folders:
        found = checks(folder)
        if not found:
            empty.append(folder)
            print(f"NONE {folder.relative_to(root).as_posix()}/ (no executable file)", flush=True)
        if args.all:
            for check in (c for c in found if skipped(c)):
                print(f"SKIP {check.relative_to(root).as_posix()} ({skipped(check)})", flush=True)
                skips += 1
            for check in (c for c in found if unlinked(c)):
                print(
                    f"NOTE {check.relative_to(root).as_posix()}: `# acceptance: skip` names no issue link,"
                    " so the marker is ignored and the check runs",
                    flush=True,
                )
            found = [c for c in found if not skipped(c)]
        for check in found:
            if run(check, root):
                passed += 1
            else:
                failed += 1
    seconds = time.monotonic() - started

    print(
        f"TOTAL {passed + failed + skips} checks, {passed} passed, {skips} skipped, {failed} failed"
        f" ({seconds:.1f}s)"
    )
    spec_minutes, nightly_minutes = budget(root)
    minutes = nightly_minutes if args.all else spec_minutes
    if seconds > minutes * 60:
        kind = "nightly" if args.all else "spec"
        print(
            f"OVER BUDGET {seconds:.1f}s > {minutes:g} min, the {kind} budget: split the slow "
            "check or move it to the nightly (a signal, not a gate)"
        )
    if failed:
        return 1
    if empty:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
