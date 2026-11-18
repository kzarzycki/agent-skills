"""The tests a change touches, for the landing gate (`mise run check-fast`): prints one pytest target per line.

The changed files come from `git diff` against the base (origin/main, or argv[1]). A changed test file runs. A changed
script runs the tests that executed the lines it changed, read from the test map the nightly builds (below), else
every test file that names its stem (any other non-markdown file: its file name). Any other file (a skill's prose,
docs, config) runs only the cheap repo-wide checks, `tests/test_skill_*.py`. No base to diff, or a change to the test
setup itself (pyproject.toml, uv.lock, mise.toml, tools/), runs everything, since the map cannot say what that touches.

The test map is `.test-map/` (env `TEST_MAP`): `coverage`, the nightly suite's coverage data with one context per test
(`pytest --cov-context=test`), and `sha`, the commit it ran on. A changed line of a script is looked up at its old
position (the diff runs from that commit), and the tests that executed it run, one node id each (a file when the id
holds a space, since the gate splits this output on whitespace, or names a test the file no longer has). The name match
is the fallback for a script the map does not hold, a map whose commit is missing, and a changed line that ran only at
import or in a subprocess, since no test is named for it. A line no test ran selects nothing: no test depends on it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ALL = ["tests", "engineering/tests"]
EVERYTHING = ("pyproject.toml", "uv.lock", "mise.toml", "tools/", "conftest.py")
MAP = Path(os.environ.get("TEST_MAP", ".test-map"))
CHEAP = sorted(str(p) for p in Path("tests").glob("test_skill_*.py"))


def changed(base: str) -> list[str] | None:
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.split() if done.returncode == 0 else None


def old_lines(sha: str, path: str) -> set[int]:
    """The lines of `path` at `sha` that the diff to HEAD changes; an insertion counts the lines around it."""
    diff = subprocess.run(
        ["git", "diff", "-U0", "--no-renames", sha, "HEAD", "--", path],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    lines: set[int] = set()
    for start, count in re.findall(r"^@@ -(\d+)(?:,(\d+))? ", diff, re.MULTILINE):
        first, n = int(start), int(count or 1)
        lines.update(range(first, first + n) if n else (first, first + 1))
    return lines


def executed_by(path: str, sha: str, data) -> set[str] | None:
    """The test node ids that ran the lines of `path` changed since `sha`; None when the name match must decide."""
    ran = data.contexts_by_lineno(path) if path in data.measured_files() else None
    if ran is None:
        return None
    ids: set[str] = set()
    for line in old_lines(sha, path):
        if ran.get(line) == [""]:  # only import or a subprocess ran it: no test is named for it
            return None
        ids |= {c.split("|")[0] for c in ran.get(line, ()) if c}
    return ids


def load_map():
    """The map's commit and coverage data, or None when there is none or its commit is gone."""
    try:
        from coverage import CoverageData

        sha = (MAP / "sha").read_text().strip()
        known = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, check=False
        )
        data = CoverageData(basename=str(MAP / "coverage"))
        data.read()
        return (sha, data) if known.returncode == 0 else None
    except ImportError, OSError:
        return None


def node_files(ids: set[str]) -> set[str]:
    """Node ids as pytest targets: the id itself when it has no whitespace and its test still exists, else its file."""
    out = set()
    for node in ids:
        file, _, name = node.partition("::")
        if not Path(file).exists():
            continue
        alive = f"def {re.split(r'[\[]', name)[0]}(" in Path(file).read_text(errors="ignore")
        out.add(node if alive and not re.search(r"\s", node) else file)
    return out


def targets(files: list[str] | None) -> list[str]:
    if files is None or any(
        f.startswith(EVERYTHING) or Path(f).name == "conftest.py" for f in files
    ):
        return ALL
    tests = [
        p for r in ALL for p in sorted(Path(r).rglob("test_*.py")) if "/e2e/" not in p.as_posix()
    ]
    picked = set(CHEAP)
    mapped = load_map()
    ran: set[str] = set()
    for f in files:
        path = Path(f)
        if path.name.startswith("test_") and path.suffix == ".py" and path.exists():
            picked.add(f)
        elif path.suffix != ".md":
            by_run = executed_by(f, *mapped) if mapped and path.suffix == ".py" else None
            if by_run is not None:
                ran |= by_run
                continue
            needle = path.stem if path.suffix == ".py" else path.name
            picked.update(str(t) for t in tests if needle in t.read_text(errors="ignore"))
    picked.update(n for n in node_files(ran) if n.split("::")[0] not in picked)
    return sorted(picked)


if __name__ == "__main__":
    print("\n".join(targets(changed(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))))
