"""The worker count `pytest -n auto` takes in this repo: the gate's GATE_JOBS when set, else the cores free when the run
starts (engineering-loop's SKILL.md, One heavy gate per host slot), never every core, since other leads' runs on the
host hold the rest. pytest-xdist calls the hook only for `-n auto`; the gate passes it when GATE_TEST_PARALLEL=1."""

from __future__ import annotations

import os

import pytest


def free_cores() -> int:
    """The cores this process may use less the host's 1-minute load, at least 1."""
    cores = os.process_cpu_count() or 1
    try:
        load = os.getloadavg()[0]
    except OSError:  # a host that doesn't say its load
        load = 0.0
    return max(1, cores - int(load))


def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    jobs = os.environ.get("GATE_JOBS", "")
    return int(jobs) if jobs.isdigit() and int(jobs) > 0 else free_cores()
