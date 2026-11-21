"""A pytest plugin (`-p tools.gate_workers`) setting the worker count `-n auto` takes: the gate's GATE_JOBS when set,
else the cores free when the run starts (engineering-loop's SKILL.md, One heavy gate per host slot), never every core,
since other leads' runs on the host hold the rest. A run under a host gate slot (tools/gate_slot.py) takes at least
its slot's share, the cores divided by the host's slot count: the 1-minute load still counts the run that held the
slot a moment ago, and the gate held the slot to get those cores. `mise run test` loads it with `-n auto` when
GATE_TEST_PARALLEL=1, `mise run check-fast` unless GATE_TEST_PARALLEL=0.
A plugin rather than a root conftest.py, since tests import their own folder's conftest by that name."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SLOT_HELD = "LOOP_GATE_SLOT_HELD"


def free_cores() -> int:
    """The cores this process may use less the host's 1-minute load, at least 1."""
    cores = os.process_cpu_count() or 1
    try:
        load = os.getloadavg()[0]
    except OSError:  # a host that doesn't say its load
        load = 0.0
    return max(1, cores - int(load))


def host_slots() -> int:
    """The host's heavy gate slot count (approvals.gate_slots), at least 1."""
    scripts = Path(__file__).resolve().parents[1] / "engineering/skills/engineering-loop/scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import approvals

    return max(1, approvals.gate_slots())


def slot_share() -> int:
    """The cores a run under a held host gate slot may take whatever the load says: the cores over the slot count,
    at least 1; 1 for a run under no slot."""
    if not os.environ.get(SLOT_HELD):
        return 1
    return max(1, (os.process_cpu_count() or 1) // host_slots())


# tryfirst: a `-p` plugin registers before pytest-xdist, whose own hook would otherwise answer first
@pytest.hookimpl(tryfirst=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    jobs = os.environ.get("GATE_JOBS", "")
    return int(jobs) if jobs.isdigit() and int(jobs) > 0 else max(free_cores(), slot_share())
