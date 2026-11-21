"""The tests a change touches, for the landing gate (`mise run check-fast`): prints one pytest target per line.

The changed files come from `git diff` against the base (origin/main, or argv[1]). A changed test file runs. A changed
script runs the tests that executed the lines it changed, read from the test map the nightly builds (below), else
every test file that names its stem (any other non-markdown file: its file name). Any other file (a skill's prose,
docs, config) runs only the cheap repo-wide checks, `tests/test_skill_*.py`. No base to diff, or a change to the test
setup itself (pyproject.toml, uv.lock, mise.toml, tools/, the root conftest.py), runs everything, since the map cannot
say what that touches. A changed conftest.py below the root runs its own folder (a target, so `collect_ignore` applies; e2e included, the gate's `-m "not live_agent"` drops
the live ones): pytest applies it to no others, and a test imports one only from its own folder (`from conftest import`). Its helper modules are scripts
like any other, so a change to one selects the tests that name it.

The test map is `.test-map/` (env `TEST_MAP`): `coverage`, the nightly suite's coverage data with one context per test
(`pytest --cov-context=test`), and `sha`, the commit it ran on. A changed line of a script is looked up at its old
position (the diff runs from that commit), and the tests that executed it run, one node id each (a file when the id
holds a space, since the gate splits this output on whitespace, or names a test the file no longer has). The name match
is the fallback for a script the map does not hold or that changed on main since it, a map whose commit is missing or
data is unreadable, and a changed line that any import or subprocess ran, since no test is named for that run. It also
adds, beside the map's tests, every test file that names the script and changed on main since the map, or can skip
(the nightly's skips leave no context). A line no test ran selects nothing: no test depends on it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ALL = ["tests", "engineering/tests"]
EVERYTHING = (
    "pyproject.toml",
    "uv.lock",
    "mise.toml",
    "tools/",
    "conftest.py",
)  # the last: the root conftest only
MAP = Path(os.environ.get("TEST_MAP", ".test-map"))
SKIPS = re.compile(r"needs_tool|skipif|pytest\.skip|importorskip")
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
        if "" in ran.get(line, ()):  # import or a subprocess ran it: no test is named for that run
            return None
        ids |= {c.split("|")[0] for c in ran.get(line, ()) if c}
    return ids


def load_map():
    """The map's commit and coverage data, or None when there is none or its commit is gone."""
    try:
        from coverage import CoverageData
        from coverage.exceptions import CoverageException
    except ImportError:
        return None
    try:
        sha = (MAP / "sha").read_text().strip()
        known = subprocess.run(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True, check=False
        )
        data = CoverageData(basename=str(MAP / "coverage"))
        data.read()
        data.measured_files()  # opens the data now: a truncated file raises here, not mid-selection
        return (sha, data) if known.returncode == 0 else None
    except OSError, CoverageException:
        return None


def moved_since(sha: str, base: str | None) -> set[str]:
    """The files that changed between the map's commit and the PR's base: the map has not seen them."""
    if base is None:
        return set()
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", sha, base],
        capture_output=True,
        text=True,
        check=False,
    )
    return set(done.stdout.split())


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


def targets(files: list[str] | None, base: str | None = None) -> list[str]:
    if files is None or any(f.startswith(EVERYTHING) for f in files):
        return ALL
    tests = [
        p for r in ALL for p in sorted(Path(r).rglob("test_*.py")) if "/e2e/" not in p.as_posix()
    ]
    picked = set(CHEAP)
    mapped = load_map()
    ran: set[str] = set()
    moved = moved_since(mapped[0], base) if mapped else set()
    for f in files:
        path = Path(f)
        if path.name == "conftest.py":
            # a conftest applies to the tests under its own folder (a test imports it only from there)
            # the folder, not its files: a file named on the command line ignores collect_ignore
            if path.parent.is_dir():
                picked.add(str(path.parent))
        elif path.name.startswith("test_") and path.suffix == ".py" and path.exists():
            picked.add(f)
        elif path.suffix != ".md":
            by_run = executed_by(f, *mapped) if mapped and path.suffix == ".py" else None
            needle = path.stem if path.suffix == ".py" else path.name
            named = {t: t.read_text(errors="ignore") for t in tests}
            named = {t: text for t, text in named.items() if needle in text}
            if by_run is not None and f not in moved:
                ran |= by_run
                # the name match stays the floor where the map is blind: a test the map has not seen (new or
                # changed on main since it) and a test the nightly may skip (it has no context)
                picked.update(
                    str(t) for t, text in named.items() if str(t) in moved or SKIPS.search(text)
                )
                continue
            picked.update(str(t) for t in named)
    picked.update(n for n in node_files(ran) if n.split("::")[0] not in picked)
    folders = [Path(p) for p in picked if Path(p).is_dir()]
    # a target under a picked folder is already collected there: naming it again would collect it twice
    return sorted(
        p
        for p in picked
        if Path(p).is_dir() or not any(Path(p.split("::")[0]).is_relative_to(d) for d in folders)
    )


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    print("\n".join(targets(changed(base), base)))
