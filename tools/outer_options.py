"""A pytest plugin (pyproject's `addopts = "-p tools.outer_options"`) that keeps the outer run's PYTEST_ADDOPTS to that
run: once pytest has read it, it leaves the environment, so a pytest a test starts as a subprocess runs with its own
options only. The nightly passes `--cov ... --cov-append` there to build the test map (tools/affected_tests.py); a
nested pytest that inherited them combined the outer run's coverage files under its own cwd's `.test-map` and erased
them, and every later test errored with `no such table: context` (#1609)."""

from __future__ import annotations

import os

import pytest


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    os.environ.pop("PYTEST_ADDOPTS", None)
