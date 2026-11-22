"""omnigent_agent.py supervise: a lead that ends its turn waiting on a process the harness does not
track (a detached pid or its log) is nudged with why nothing wakes it, then escalated (#1753)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server, the supervisor loop
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    no_loop_events,
    no_model,
    no_sleep,
    this_repo,
    trusted_folders,
)

omnigent_agent = base.omnigent_agent

OBSERVED = "STILL WORKING: waiting on pid 4242 (the build, started with nohup)"


def route(text: str, **event: object) -> tuple[str, str, str]:
    return omnigent_agent.route({"kind": "ended", "last": text, **event}, lambda: ("none", "fake"))


@pytest.mark.parametrize(
    "text",
    [
        OBSERVED,
        "STILL WORKING: waiting on tmp/loop/gate.log",
        "STILL WORKING: waiting on the build, pid 4242",
        "STILL WORKING: build started.\nWaiting on its pid file before the push.",
    ],
)
def test_a_wait_on_a_pid_or_a_log_is_nudged_once_then_escalated(text: str) -> None:
    assert route(text) == (
        "rule",
        "nudge",
        f"{omnigent_agent.UNTRACKED_WHY}: nothing wakes it when that ends",
    )
    assert route(text, nudged=True) == (
        "rule",
        "act",
        f"{omnigent_agent.UNTRACKED_WHY} again after its nudge",
    )
    # the same words again after the nudge escalate rather than read as a repeat
    assert route(text, nudged=True, repeat=True)[1] == "act"


@pytest.mark.parametrize(
    ("text", "wait"),
    [
        ("STILL WORKING: waiting on pid 4242, started with LOOP_NOTIFY set", "pid"),
        ("STILL WORKING: waiting on the gate (wait-for --notify on gate.log)", "the"),
        ("STILL WORKING: waiting on the verifier (its log is tmp/loop/v.log)", "verifier"),
        ("STILL WORKING: waiting on CI; gate.log was clean", "CI"),
        ("STILL WORKING: waiting on pid 4242\nWaits: CI", "CI"),
        ("STILL WORKING: waiting on deployment", "deployment"),
    ],
)
def test_a_wait_that_wakes_the_lead_by_itself_keeps_its_route(text: str, wait: str) -> None:
    assert not omnigent_agent.untracked_wait(text)
    if wait != "the":
        assert route(text) == ("rule", "record", f"names its wait: {wait}")


def test_the_supervisor_sends_the_untracked_wait_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = base.following(tmp_path)
    offset = base.skewed(monkeypatch)
    og = base.Lead(base.told("brief", 60), base.ending(OBSERVED, 0))
    base.supervised(
        og,
        registry,
        monkeypatch,
        2,
        lambda p: offset.__setitem__(0, 301.0),
        notify="cos",
        console=True,
    )
    assert [t for s, t in og.inbox if s == "a"] == [omnigent_agent.LEAD_UNTRACKED]
    assert base.events_of(registry)[-1]["action"] == "nudge"
    # the lead fixes its own wait: nothing goes to the chief of staff yet
    assert base.posted(og) == []
