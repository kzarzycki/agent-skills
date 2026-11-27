"""The nightly's test map, pruned to the tests that passed and checked before it is saved (#1400).

`python3 tools/test_map_check.py <map dir>` (the nightly's `.test-map`) does two things, in order:

- Prune: each test the run recorded as failed (`failed`, from tools/test_map_plugin.py) loses its coverage contexts, so one
  red test leaves the map of every test that passed, not no map at all. A test missing from the map falls back to the
  selector's name match, as before.
- Check: the map must measure at least one source file and name every test that ran and passed (the run's `durations.log`,
  less `failed` and `skipped`). An empty map, or one short of a test, exits 1 with the reason, so a nightly never saves
  a map the selector would quietly ignore. A test file the checkout no longer has is no test of this run (a nested pytest
  in a temp directory writes its own lines to the same log).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

PHASES = ("setup", "run", "teardown")  # the phases pytest-cov and tools/test_map_plugin.py name a context by
SHOWN = 5  # the tests an error names, since the rest are the same fault


def lines(path: Path) -> set[str]:
    try:
        return {line.strip() for line in path.read_text().splitlines() if line.strip()}
    except OSError:
        return set()


def prune(coverage: Path, failed: set[str]) -> int:
    """Drop the contexts of the `failed` test ids from the coverage data at `coverage`; the number of rows dropped."""
    if not failed or not coverage.exists():
        return 0
    names = [f"{node}|{phase}" for node in failed for phase in PHASES]
    with sqlite3.connect(coverage) as db:
        marks = ",".join("?" * len(names))
        ids = [i for (i,) in db.execute(f"select id from context where context in ({marks})", names)]
        dropped = 0
        for table in ("line_bits", "arc"):
            try:
                marks = ",".join("?" * len(ids))
                dropped += db.execute(
                    f"delete from {table} where context_id in ({marks})", ids
                ).rowcount
            except sqlite3.OperationalError:  # the data has no such table (lines only, or arcs only)
                pass
    return dropped


def named_tests(coverage: Path) -> tuple[set[str], set[str]]:
    """The test node ids the map has a context for, and the source files it measures (not test files)."""
    with sqlite3.connect(coverage) as db:
        used = {
            c
            for (c,) in db.execute(
                "select distinct context from context where id in (select context_id from line_bits)"
            )
        }
        paths = {p for (p,) in db.execute("select path from file")}
    tests = {c.rsplit("|", 1)[0] for c in used if c}
    sources = {
        p for p in paths if "/tests/" not in f"/{p}" and not Path(p).name.startswith(("test_", "conftest"))
    }
    return tests, sources


def ran_ok(log: Path, failed: set[str], skipped: set[str]) -> set[str]:
    """The tests this run ran and passed: the `call` lines of `durations.log` (`<seconds>s <phase> <node id>`) of a test
    file the checkout holds, less the failed and the skipped."""
    ran = set()
    for line in lines(log):
        words = line.split(None, 2)
        if len(words) == 3 and words[1] == "call" and Path(words[2].split("::")[0]).exists():
            ran.add(words[2])
    return ran - failed - skipped


def problems(root: Path) -> list[str]:
    """What is wrong with the map under `root` (empty when it is fit to save)."""
    coverage = root / "coverage"
    if not coverage.exists():
        return [f"map is empty: no coverage data at {coverage}"]
    try:
        tests, sources = named_tests(coverage)
    except sqlite3.DatabaseError as error:
        return [f"map is unreadable: {error}"]
    if not sources:
        return ["map is empty: it measures no source file"]
    if not tests:
        return ["map is empty: it names no test (a run under xdist records no contexts)"]
    missing = sorted(ran_ok(root / "durations.log", lines(root / "failed"), lines(root / "skipped")) - tests)
    if missing:
        shown = ", ".join(missing[:SHOWN]) + (" ..." if len(missing) > SHOWN else "")
        return [f"map names fewer tests than ran: {len(missing)} passed with no context, e.g. {shown}"]
    return []


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".test-map")
    dropped = prune(root / "coverage", lines(root / "failed"))
    if dropped:
        print(f"test-map: dropped {dropped} rows of {len(lines(root / 'failed'))} failed tests")
    found = problems(root)
    for line in found:
        print(f"test-map: {line}", file=sys.stderr)
    if not found:
        tests, sources = named_tests(root / "coverage")
        print(f"test-map: {len(tests)} tests, {len(sources)} source files")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
