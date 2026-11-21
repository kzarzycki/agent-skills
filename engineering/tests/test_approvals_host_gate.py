"""approvals.py: `land: host_gate: false` never runs a gate on the host `land` runs on (#1663)."""

from __future__ import annotations

import time as real_time
from typing import Any

import pytest
from approvals_harness import GITHUB_RULE, approvals, git_in, lands  # noqa: F401

TIMEOUT = 100


class Clock:
    """A stubbed `time`: `sleep` moves `monotonic` by what it is asked, then runs `tick(now)`."""

    def __init__(self) -> None:
        self.now, self.slept, self.tick = 0.0, [], lambda _now: None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert 0 < seconds and sum(self.slept) < 10_000, "the wait never ends"
        self.slept.append(seconds)
        self.now += seconds
        self.tick(self.now)

    def __getattr__(self, name: str) -> Any:
        return getattr(real_time, name)


@pytest.fixture(autouse=True)
def checks_required(monkeypatch: pytest.MonkeyPatch, required: list[str]) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check"})


@pytest.fixture
def cloud(
    lands: dict[str, Any], refs: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """No cloud push, session or real wait: `asked` holds each tree the session was asked to gate, `ask` the reason a
    start fails with, and `record(tree)` puts a record branch for `tree` on origin."""
    clock = Clock()
    monkeypatch.setattr(approvals, "time", clock)
    state: dict[str, Any] = {"asked": [], "ask": "", "clock": clock}
    real = approvals.git

    def git(*args: str, **kw: Any) -> str:
        if args[:1] == ("push",) and "loop-land" in args[-1]:
            return ""
        return real(*args, **kw)

    def ask(tree: str) -> str:
        state["asked"].append(tree)
        return state["ask"]

    def record(tree: str) -> None:
        command, _, env = approvals.gate()
        refs[approvals.record_name(tree, command)] = {
            "head": "c" * 40,
            "tree": tree,
            "command": command,
            "time": "2026-01-01T00:00:00Z",
            "env": env,
        }

    monkeypatch.setattr(approvals, "git", git)
    monkeypatch.setattr(approvals, "ask_cloud_gate", ask)
    monkeypatch.setattr(approvals, "gate_ended", lambda _tree: "")
    state["record"] = record
    return state


def policy(lands: dict[str, Any], setting: str) -> None:
    """The base's policy with `setting` (a section), committed to origin's main before any PR is opened."""
    work = lands["work"]
    (work / "docs" / "agents" / "loop.md").write_text(
        GITHUB_RULE.replace("```yaml\n", f"```yaml\n{setting}\n", 1)
    )
    git_in(work, "add", "docs")
    git_in(work, "commit", "-q", "-m", "policy")
    git_in(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git_in(work, "fetch", "-q", "origin")


CLOUD_ONLY = f"land:\n  gate_on: cloud\n  cloud_gate_timeout_seconds: {TIMEOUT}\n  host_gate: false"


def test_a_cloud_record_lands_with_no_host_gate(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, CLOUD_ONLY)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["clock"].tick = lambda now: cloud["record"](cloud["asked"][0]) if now >= 60 else None
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 0), lines


@pytest.mark.parametrize("fault", ["timeout", "refused"])
def test_a_missing_cloud_record_refuses_and_runs_nothing_on_the_host(
    lands: dict[str, Any], cloud: dict[str, Any], fault: str
) -> None:
    policy(lands, CLOUD_ONLY)
    lands["open"](7, {"7.txt": "7\n"})
    if fault == "refused":
        cloud["ask"] = "start refused: out of capacity"
    code, lines = lands["land"]("7")
    [tree] = cloud["asked"]
    assert code != 0 and lands["merged"]() == [] and lands["runs"]() == 0, lines
    assert any(f"no cloud record for tree {tree}" in line for line in lines), lines
    assert not any("gating on this host" in line for line in lines), lines


def test_without_gate_on_a_tree_with_no_record_refuses_too(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, "land:\n  host_gate: false")
    lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]("7")
    assert code != 0 and lands["merged"]() == [] and lands["runs"]() == 0, lines
    assert any("no cloud record for tree " in line for line in lines), lines
    assert cloud["asked"] == []


def test_host_gate_true_keeps_the_host_fallback(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, CLOUD_ONLY.replace("false", "true"))
    lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 1), lines
    assert any("gating on this host" in line for line in lines), lines


def test_a_host_only_step_needs_a_record_too(monkeypatch: pytest.MonkeyPatch) -> None:
    steps = [
        {"name": "unit", "where": "any"},
        {"name": "apple", "where": "host"},
    ]
    monkeypatch.setattr(approvals, "gate_plan", lambda *_a: steps)
    monkeypatch.setattr(approvals, "settings", lambda _loop: {"land": {"host_gate": False}})
    monkeypatch.setattr(
        approvals,
        "step_pass",
        lambda _h, _t, step, show=True: {"exit": 0} if step["name"] == "unit" else None,
    )
    with pytest.raises(approvals.Refused, match="no cloud record for tree t1.*`apple`"):
        approvals.no_host_gate("a" * 40, "t1")


def test_host_gate_must_be_a_boolean() -> None:
    block = GITHUB_RULE.replace("```yaml\n", "```yaml\nland:\n  host_gate: never\n", 1)
    with pytest.raises(
        approvals.Refused, match="`land.host_gate` must be true or false, not 'never'"
    ):
        approvals.settings(block)
