"""A pytest plugin (pyproject's `addopts = "-p tools.test_map_plugin"`) that keeps the nightly's test map
(tools/affected_tests.py) whole and naming its tests (#1609).

- The outer run's PYTEST_ADDOPTS stays with it: once pytest has read it, it leaves the environment, so a pytest a test
  starts as a subprocess runs with its own options only. The nightly passes `--cov ... --cov-append` there; a nested
  pytest that inherited them combined the outer run's per-process coverage files and erased them, and every later
  test errored with `no such table: context`.
- A subprocess a test starts is measured under that test. coverage's `patch = ["subprocess"]` hands a child the
  parent's configuration, serialized once at start (COVERAGE_PROCESS_CONFIG, base64 JSON), whose static `context` is
  empty, so every line a test reached only through a subprocess (most of `approvals.py`) carried no test and sent the
  selector to the name match. While a test runs, that configuration names the test as its context instead. A
  configuration this can't read is left as it is: the child is then measured as before.
- A test the run skips leaves no context, so with SKIPPED set (the nightly sets it to `.test-map/skipped`) each skipped
  test's node id goes there, one per line, and the selector runs those beside the map's tests.
"""

from __future__ import annotations

import base64
import json
import os

import pytest

CONFIG = "COVERAGE_PROCESS_CONFIG"
SKIPPED = "TEST_MAP_SKIPPED"


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    os.environ.pop("PYTEST_ADDOPTS", None)


def with_context(serialized: str, context: str) -> str | None:
    """`serialized` (a CoverageConfig.serialize() string) with its static context set to `context`; None if unreadable."""
    try:
        data = json.loads(base64.b64decode(serialized.encode()).decode())
    except ValueError:
        return None
    if not isinstance(data, dict) or "context" not in data:
        return None
    data["context"] = context
    return base64.b64encode(json.dumps(data).encode()).decode()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    before = os.environ.get(CONFIG)
    # `|run`: the phase pytest-cov's own test contexts carry, so the selector reads both alike
    named = with_context(before, f"{item.nodeid}|run") if before else None
    if named is not None:
        os.environ[CONFIG] = named
    try:
        return (yield)
    finally:
        if named is not None and before is not None:
            os.environ[CONFIG] = before


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped and (path := os.environ.get(SKIPPED)):
        with open(path, "a") as out:
            out.write(f"{report.nodeid}\n")
