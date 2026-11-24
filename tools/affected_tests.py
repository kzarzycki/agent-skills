"""The tests a change touches, for the Mergify batch (`mise run test-batch`): prints one pytest target per line.

The changed files come from `git diff` against the base (origin/main, or argv[1]). A changed test file runs. A changed
script runs the tests that executed the lines it changed, read from the test map the nightly builds (below), else
every test file that names its stem (any other non-markdown file: its file name). Any other file (a skill's prose,
docs, config) runs only the cheap repo-wide checks, `tests/test_skill_*.py`. It never selects the whole suite (#1872):
with no base to diff it can't tell what changed, so it runs nothing and says so, and a change to the test setup itself
(pyproject.toml, uv.lock, mise.toml, a conftest.py), which the map cannot judge, runs only the tests that name it, as
any other non-markdown file does.

The test map is `.test-map/` (env `TEST_MAP`): `coverage`, the nightly suite's coverage data with one context per test
(`pytest --cov-context=test`), and `sha`, the commit it ran on. A changed line of a script is looked up at its old
position (the diff runs from that commit), and the tests that executed it run, one node id each (a file when the id
holds a space, since the gate splits this output on whitespace, or names a test the file no longer has). The name match
is the fallback for a script the map does not hold or that changed on main since it, a map whose commit is missing or
data is unreadable, and a changed line that any import or subprocess ran, since no test is named for that run. A
line beside an inserted whole new undecorated function or class is not changed, so its import run is no reason;
beside any other insertion (a decorator, a constant, an import) it counts as changed, since that code runs at import. It also
adds, beside the map's tests, every test file that names the script and changed on main since the map, and of those
files the tests the nightly skipped (a skip leaves no context): by node id from the map's `skipped` list, else, for a
map without one, every such file that can skip. A line no test ran selects nothing: no test depends on it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ALL = [
    "tests",
    "engineering/tests",
    "gatekeeper/tests",
    "loop/tests",
    "github/tests",
    "chief-of-staff/tests",
    "omnigent/tests",
]
SETUP = ("pyproject.toml", "uv.lock", "mise.toml", "conftest.py")
MAP = Path(os.environ.get("TEST_MAP", ".test-map"))
SKIPS = re.compile(r"needs_tool|skipif|pytest\.skip|importorskip")
CHEAP = sorted(str(p) for p in Path("tests").glob("test_skill_*.py"))
# docs a test holds byte for byte against a copy, which no name match finds: a change to one runs that test
DOC_TESTS = {
    "loop/skills/engineering-loop/": "tests/test_old_paths.py",
    "engineering/skills/engineering-loop/": "tests/test_old_paths.py",
}


def changed(base: str) -> list[str] | None:
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.split() if done.returncode == 0 else None


HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? [^\n]*\n((?:[-+ \\][^\n]*\n?)*)", re.MULTILINE)
NEW_BLOCK = re.compile(r"(?:async\s+def|def|class)\s")


def new_block(added: list[str]) -> bool:
    """Whether inserted lines are only whole new undecorated `def`s or `class`es (blank lines between): code no import
    runs but its definition, so no existing test runs it until a changed caller does."""
    lines = [line for line in added if line.strip()]
    if not lines or not NEW_BLOCK.match(lines[0].lstrip()):
        return False
    indent = len(lines[0]) - len(lines[0].lstrip())
    for line in lines:
        depth = len(line) - len(line.lstrip())
        if depth < indent or (depth == indent and not NEW_BLOCK.match(line.lstrip())):
            return False  # a decorator, a constant, a statement at the block's own level
    return True


def old_lines(sha: str, path: str) -> tuple[set[int], set[int]]:
    """The lines of `path` at `sha` that the diff to HEAD changes, and the lines around each insertion of whole new
    undecorated functions or classes (new_block), which stand for that code without being changed themselves. Any
    other insertion counts the lines around it as changed: a decorator or a module-level line runs at import."""
    diff = subprocess.run(
        ["git", "diff", "-U0", "--no-renames", sha, "HEAD", "--", path],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    changed: set[int] = set()
    around: set[int] = set()
    for start, count, body in HUNK.findall(diff):
        first, n = int(start), int(count or 1)
        if n:
            changed.update(range(first, first + n))
        else:
            added = [line[1:] for line in body.splitlines() if line.startswith("+")]
            (around if new_block(added) else changed).update((first, first + 1))
    return changed, around - changed


def executed_by(path: str, sha: str, data) -> set[str] | None:
    """The test node ids that ran the lines of `path` changed since `sha`; None when the name match must decide."""
    ran = data.contexts_by_lineno(path) if path in data.measured_files() else None
    if ran is None:
        return None
    ids: set[str] = set()
    changed, around = old_lines(sha, path)
    for line in changed | around:
        # import or a subprocess ran a changed line: no test is named for that run. A line beside a new function or
        # class (old_lines) is not changed, so the import that ran it (the `def` line above, say) says nothing of
        # that code: only the tests that ran it count.
        if line in changed and "" in ran.get(line, ()):
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


def skipped() -> set[str] | None:
    """The node ids the map's run skipped (`skipped` beside it, from tools/test_map_plugin.py), or None for a map with no
    such list, whose skips are then guessed from the test files' text (SKIPS)."""
    try:
        return set((MAP / "skipped").read_text().split())
    except OSError:
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
    """Node ids as pytest targets: the id itself when it has no whitespace and its test still exists; a parametrized id
    with whitespace (the gate splits on it) as its test function, every parameter of it; else its file."""
    out = set()
    for node in ids:
        file, _, name = node.partition("::")
        if not Path(file).exists():
            continue
        function = re.split(r"[\[]", name)[0]  # `test_x`, or `TestK::test_x` in a class
        alive = f"def {function.rsplit('::', 1)[-1]}(" in Path(file).read_text(errors="ignore")
        if alive and not re.search(r"\s", node):
            out.add(node)
        elif alive and not re.search(r"\s", function):
            out.add(f"{file}::{function}")
        else:
            out.add(file)
    return out


PACKAGE_CODE = re.compile(r"^([^/]+)/(?:[^/]+/)*(?:scripts|src)/[^/]+\.py$")


def package_tests(path: str, tests: list[Path]) -> list[str]:
    """Every test file of the package whose `scripts/` or `src/` holds `path`, else none: the fallback when no test
    is found for a changed script, since a change nothing names or ran is not one nothing depends on (#2157)."""
    m = PACKAGE_CODE.match(path)
    if not m or f"{m[1]}/tests" not in ALL:
        return []
    return [str(t) for t in tests if t.as_posix().startswith(f"{m[1]}/tests/")]


def say(line: str) -> None:
    """One line on stderr naming the rule that picked a target, so a slow run's log shows why it ran what it did."""
    print(f"affected-tests: {line}", file=sys.stderr)


def targets(files: list[str] | None, base: str | None = None) -> list[str]:
    if files is None:
        say(
            f"nothing: no diff against {base}, so it can't tell what changed, and never the whole suite"
        )
        return []
    for f in files:
        if f.startswith(SETUP) or Path(f).name == "conftest.py":
            say(
                f"{f}: test setup, which the map cannot judge: only the tests that name it run, never the suite"
            )
    tests = [
        p for r in ALL for p in sorted(Path(r).rglob("test_*.py")) if "/e2e/" not in p.as_posix()
    ]
    picked = set(CHEAP)
    mapped = load_map()
    say(
        f"map of {mapped[0][:12]}"
        if mapped
        else f"no map at {MAP}: a script runs every test that names it"
    )
    ran: set[str] = set()
    moved = moved_since(mapped[0], base) if mapped else set()
    skips = skipped() if mapped else None
    for f in files:
        path = Path(f)
        if (
            path.name.startswith("test_")
            and path.suffix == ".py"
            and path.exists()
            and f.startswith(tuple(f"{r}/" for r in ALL))
        ):  # a test file under a suite root; `tools/test_map_plugin.py` is a plugin, which the name match covers
            picked.add(f)
            say(f"{f}: a changed test")
        elif path.suffix == ".md":
            for prefix, test in DOC_TESTS.items():
                if f.startswith(prefix):
                    picked.add(test)
                    say(f"{f}: {test} holds a copy of it")
        else:
            by_run = executed_by(f, *mapped) if mapped and path.suffix == ".py" else None
            needle = path.stem if path.suffix == ".py" else path.name
            named = {t: t.read_text(errors="ignore") for t in tests}
            named = {t: text for t, text in named.items() if needle in text}
            if by_run is not None and f not in moved:
                say(f"{f}: {len(by_run)} tests from the map")
                ran |= by_run
                # the name match stays the floor where the map is blind: a test the map has not seen (new or
                # changed on main since it) and a test the nightly may skip (it has no context)
                floor = {
                    str(t)
                    for t, text in named.items()
                    if str(t) in moved or (skips is None and SKIPS.search(text))
                }
                picked.update(floor)
                skipped_here = set()
                if skips is not None:  # the tests of these files the map's run skipped, by node id
                    skipped_here = {n for n in skips if n.split("::")[0] in {str(t) for t in named}}
                    ran |= skipped_here
                if (
                    not by_run
                    and not floor
                    and not skipped_here
                    and (pkg := package_tests(f, tests))
                ):
                    say(f"{f}: no test ran it: the package's {len(pkg)} test files")
                    picked.update(pkg)
                continue
            if mapped and path.suffix == ".py":
                why = (
                    "changed on main since the map"
                    if f in moved
                    else "not in the map, or an import ran its change"
                )
                say(f"{f}: {len(named)} test files name it ({why})")
            else:
                say(f"{f}: {len(named)} test files name it")
            picked.update(str(t) for t in named)
            if not named and (pkg := package_tests(f, tests)):
                say(f"{f}: no test names it: the package's {len(pkg)} test files")
                picked.update(pkg)
    picked.update(n for n in node_files(ran) if n.split("::")[0] not in picked)
    return sorted(picked)


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    print("\n".join(targets(changed(base), base)))
