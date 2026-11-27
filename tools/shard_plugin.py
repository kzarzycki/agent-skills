"""A pytest plugin (pyproject's `addopts = "-p tools.shard_plugin"`) that splits one run into disjoint shards that run at the
same time, for the scheduled full run (#2804).

The nightly's test-map run is serial: under xdist `--cov-context=test` records no per-test contexts, so the map would name no
test (#1610). One process on a 4-core runner took 52 minutes in November and the suite grows, so it hit the 60-minute
`timeouts.run` limit. The same serial runs, a few at a time, each on a share of the test files, keep every per-test context
and finish in a fraction of the time. This plugin is that split; it does nothing unless `TEST_SHARDS` is above 1.

- With `TEST_SHARDS=<n>` the outer pytest runs no test itself: it starts `n` pytest processes with the same arguments and
  environment, waits for them, and exits with their worst status (a shard that selected no test counts as passing). Each
  shard writes its own coverage data (`COVERAGE_FILE-shard<i>`), skipped list (`TEST_MAP_SKIPPED-shard<i>`), failed list (`TEST_MAP_FAILED-shard<i>`) and durations
  (`TEST_DURATIONS-shard<i>`), so no two processes append to one file; the outer run folds them back into the names the nightly
  set (`coverage combine --append`, then the two lists appended), the one map and lists a serial run leaves.
- A shard (`SHARD_INDEX` and `SHARD_COUNT` in its environment) keeps the test files whose greedy split by test count puts them
  on its index and deselects the rest. Every shard collects the same tests, so the split is the same in each.
- Both variables are read when pytest starts and removed from the environment, so a pytest a test starts, which inherits
  the environment, runs whole.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SHARDS = "TEST_SHARDS"
INDEX = "SHARD_INDEX"
COUNT = "SHARD_COUNT"
OWN = "COVERAGE_FILE", "TEST_MAP_SKIPPED", "TEST_DURATIONS", "TEST_MAP_FAILED"  # the files a shard keeps apart
NO_TESTS = 5  # pytest's exit status for a run that collected nothing


def split(counts: dict[str, int], shards: int) -> dict[str, int]:
    """The shard of each file, by greedy balance on its test count (the biggest file to the lightest shard first)."""
    load = [0] * shards
    held: dict[str, int] = {}
    for path in sorted(counts, key=lambda p: (-counts[p], p)):
        lightest = min(range(shards), key=lambda i: (load[i], i))
        held[path] = lightest
        load[lightest] += counts[path]
    return held


def shard_files(shards: int) -> list[dict[str, str]]:
    """Each shard's environment overrides: its index and count, and its own copy of the files in OWN that are set."""
    out = []
    for i in range(shards):
        env = {INDEX: str(i), COUNT: str(shards), SHARDS: ""}
        for name in OWN:
            if base := os.environ.get(name):
                env[name] = f"{base}-shard{i}"
        out.append(env)
    return out


def fold(shards: int) -> None:
    """Put each shard's coverage data, skipped list and durations into the files a serial run would have written."""
    base = os.environ.get("COVERAGE_FILE")
    parts = [
        f"{base}-shard{i}" for i in range(shards) if base and Path(f"{base}-shard{i}").exists()
    ]
    if parts:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "coverage",
                "combine",
                "--append",
                f"--data-file={base}",
                *parts,
            ],
            check=False,
        )
    for name in ("TEST_MAP_SKIPPED", "TEST_DURATIONS", "TEST_MAP_FAILED"):
        target = os.environ.get(name)
        if not target:
            continue
        for i in range(shards):
            part = Path(f"{target}-shard{i}")
            if part.exists():
                with open(target, "a") as out:
                    out.write(part.read_text())
                part.unlink()


def run_shards(args: list[str], shards: int) -> int:
    """Start the shards, print each one's output as it ends, and return the worst status."""
    procs = []
    for i, extra in enumerate(shard_files(shards)):
        log = Path(f"shard-{i}.log")
        out = open(log, "w")  # noqa: SIM115 - held for the child's life
        env = {**os.environ, **extra}
        env.pop(SHARDS, None)
        procs.append(
            (
                i,
                log,
                out,
                subprocess.Popen(
                    [sys.executable, "-m", "pytest", *args],
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    env=env,
                ),
            )
        )
    worst = 0
    for i, log, out, proc in procs:
        status = proc.wait()
        out.close()
        print(f"===== shard {i + 1}/{shards}: exit {status} =====", flush=True)
        print(log.read_text(), flush=True)
        log.unlink()
        if status not in (0, NO_TESTS):
            worst = max(worst, status)
    fold(shards)
    return worst


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config: pytest.Config) -> int | None:
    asked = os.environ.get(SHARDS, "")
    if asked.isdigit() and int(asked) > 1 and INDEX not in os.environ:
        return run_shards([str(a) for a in config.invocation_params.args], int(asked))
    return None


def pytest_configure(config: pytest.Config) -> None:
    index, count = os.environ.pop(INDEX, ""), os.environ.pop(COUNT, "")
    os.environ.pop(SHARDS, None)
    config.stash_shard = (int(index), int(count)) if index.isdigit() and count.isdigit() else None  # type: ignore[attr-defined]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mine = getattr(config, "stash_shard", None)
    if not mine:
        return
    index, count = mine
    counts: dict[str, int] = {}
    for item in items:
        counts[str(item.path)] = counts.get(str(item.path), 0) + 1
    held = split(counts, count)
    kept = [item for item in items if held[str(item.path)] == index]
    gone = [item for item in items if held[str(item.path)] != index]
    if gone:
        config.hook.pytest_deselected(items=gone)
    items[:] = kept
