"""`land --wait`'s poll round between two landing() rounds: what each wait state may ask GitHub (#1915).

A round of landing() reads every named PR, the base's rules and its open PRs; with several lands waiting at once its
poll burned the account's REST quota in minutes. Between rounds a wait now reads only what it waits on: a held lock
with one `git ls-remote` and no gh call at all, a named PR's CI with one ls-remote and two ETag reads per head, which
GitHub answers 304, at no quota, while nothing changed. The budgets below fail a change that spends more.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
from typing import Any

import pytest
from approvals_harness import approvals

github = approvals.github

LOCK = "refs/heads/loop-landing/main"
HEAD = "a" * 40
BASE_TIP = "b" * 40
# a poll round's budget per wait state: gh calls (REST quota a 200 spends) and git ls-remote calls
LOCK_GH, CI_GH_PER_HEAD, LS_REMOTES = 0, 2, 1


class Hub:
    """`gh` faked at subprocess.run under the real github.gh(): it answers the ETag reads of a head's check runs and
    statuses, 304 to an If-None-Match that still matches, and counts every call."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.guards: list[list[str]] = []
        self.runs = [{"name": "check", "status": "in_progress", "conclusion": None}]
        self.statuses: list[dict[str, str]] = []
        self.exit_on_304 = True  # gh exits 1 on a 304, printing `gh: HTTP 304`

    def body(self, path: str) -> dict[str, Any]:
        if "check-runs" in path:
            return {"total_count": len(self.runs), "check_runs": self.runs}
        return {"state": "pending", "statuses": self.statuses}

    def __call__(self, cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        # the wait's quota guard, which GitHub does not count
        if cmd[:3] == ["gh", "api", "rate_limit"]:
            self.guards.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "5000 5000 0", "")
        assert cmd[:3] == ["gh", "api", "-i"], cmd
        self.calls.append(cmd)
        body = json.dumps(self.body(cmd[-1]))
        etag = f'"{abs(hash(body))}"'
        if f"If-None-Match: {etag}" in cmd:
            if self.exit_on_304:
                raise subprocess.CalledProcessError(
                    1, cmd, "HTTP/2.0 304 Not Modified\nEtag: " + etag + "\n\n", "gh: HTTP 304"
                )
            return subprocess.CompletedProcess(cmd, 0, "HTTP/2.0 304 Not Modified\n\n", "")
        return subprocess.CompletedProcess(cmd, 0, f"HTTP/2.0 200 OK\nEtag: {etag}\n\n{body}", "")


class Origin:
    """`git` as the wait's probe runs it: ls-remote of the lock, base and PR heads; fetch and log of a lock tip."""

    def __init__(self) -> None:
        self.lock = "l0"
        self.parents = {"l0": ""}  # lock commit -> (title, parent)
        self.titles = {"l0": approvals.HELD}
        self.base = BASE_TIP
        self.head = HEAD
        self.ls: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        if args[0] == "ls-remote":
            self.ls.append(args)
            tips = {LOCK: self.lock, "refs/heads/main": self.base, "refs/pull/7/head": self.head}
            return "".join(f"{tips[ref]}\t{ref}\n" for ref in args[2:] if ref in tips)
        if args[0] == "fetch":
            return ""
        if args[0] == "log":
            return f"{self.titles[args[-1]]} [skip ci]\0{self.parents[args[-1]]}\n"
        raise AssertionError(args)

    def stamp(self, title: str = approvals.HELD) -> None:
        """The lock moves on to a child: a heartbeat (HELD) or a release (FREE)."""
        new = f"l{len(self.parents)}"
        self.parents[new], self.titles[new], self.lock = self.lock, title, new


@pytest.fixture
def wait(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A land --wait on PR #7 under a fake clock, whose landing() rounds are recorded, not run: each says it waits on
    the lock (`held`) or on CI."""
    state: dict[str, Any] = {"now": 0.0, "rounds": [], "held": True, "events": [], "ticks": []}
    hub, origin = Hub(), Origin()
    state.update(hub=hub, origin=origin)

    def landing(pr: Any, only: bool = False) -> tuple[int, bool]:
        state["rounds"].append(state["now"])
        pull = {
            "number": 7,
            "headRefName": "feature",
            "headRefOid": origin.head,
            "baseRefOid": origin.base,
        }
        approvals.watched.update(base="main", pulls=[pull], required={"check"})
        if state["held"]:
            approvals.held_tip = (LOCK, origin.lock)
        return approvals.WAITING, True

    def sleep(seconds: float) -> None:
        state["now"] += seconds
        for at, act in list(state["ticks"]):
            if state["now"] >= at:
                state["ticks"].remove((at, act))
                act()

    monkeypatch.setattr(github, "wait_until", None)
    monkeypatch.setattr(github.subprocess, "run", hub)
    monkeypatch.setattr(github, "etags", {})
    monkeypatch.setattr(approvals, "poll_seconds", lambda *_: approvals.QUEUE_POLL)
    monkeypatch.setattr(approvals.time, "monotonic", lambda: state["now"])
    monkeypatch.setattr(approvals.time, "sleep", sleep)
    monkeypatch.setattr(approvals, "landing", landing)
    monkeypatch.setattr(approvals, "git", origin)
    monkeypatch.setattr(approvals, "land_event", lambda pull, s, *a, **k: state["events"].append(s))
    monkeypatch.setattr(approvals, "CEILING", 1800)
    return state


def before_ceiling(state: dict[str, Any]) -> list[float]:
    """The landing() rounds before the one a wait runs as it reaches its ceiling."""
    return [at for at in state["rounds"] if at < approvals.CEILING]


def poll_rounds(state: dict[str, Any]) -> int:
    """The poll steps the wait slept between landing() rounds."""
    return int(state["now"] // approvals.POLL)  # a landing() round takes no time on the fake clock


def test_a_poll_round_behind_a_held_lock_makes_no_gh_call(wait: dict[str, Any]) -> None:
    for at in range(300, 1800, 300):  # the holder's heartbeat moves the lock every BEAT
        wait["ticks"].append((at, wait["origin"].stamp))
    assert approvals.land(7, wait=True) == approvals.WAITING
    # a live holder's lock is never asked of GitHub again before the ceiling's last round
    assert before_ceiling(wait) == [0.0]
    assert len(wait["hub"].calls) == LOCK_GH * poll_rounds(wait)
    assert len(wait["origin"].ls) <= LS_REMOTES * poll_rounds(wait)
    assert "waiting" in wait["events"]  # the PR's `waiting` event is still beaten, by git push


def test_a_released_lock_runs_the_round_at_the_next_poll(wait: dict[str, Any]) -> None:
    wait["ticks"].append((600, lambda: wait["origin"].stamp(approvals.FREE)))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, 600.0]


def test_a_lock_that_stops_beating_runs_the_round_once_stale(wait: dict[str, Any]) -> None:
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.STALE)]


@pytest.mark.parametrize("exit_on_304", [True, False])
def test_a_poll_round_of_a_wait_on_ci_spends_no_quota_while_nothing_changed(
    wait: dict[str, Any], exit_on_304: bool
) -> None:
    wait["held"] = False
    wait["hub"].exit_on_304 = exit_on_304
    approvals.land(7, wait=True)
    rounds, hub = poll_rounds(wait), wait["hub"]
    # nothing moved: only FULL runs the round again
    assert before_ceiling(wait) == [0.0, float(approvals.FULL)]
    assert len(hub.calls) <= CI_GH_PER_HEAD * rounds
    # each round after the first asks with the ETag of the last answer, which GitHub answers 304 at no quota
    first = {call[-1] for call in hub.calls[:CI_GH_PER_HEAD]}
    plain = [call for call in hub.calls if not any(a.startswith("If-None-Match") for a in call)]
    assert len(plain) == len(first) == CI_GH_PER_HEAD
    assert len(wait["origin"].ls) <= LS_REMOTES * rounds


def test_a_required_check_that_completes_runs_the_round_after_its_poll(
    wait: dict[str, Any],
) -> None:
    wait["held"] = False

    def done() -> None:
        wait["hub"].runs = [{"name": "check", "status": "completed", "conclusion": "success"}]

    wait["ticks"].append((120, done))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.QUEUE_POLL)]


def test_a_check_the_base_does_not_require_runs_no_round(wait: dict[str, Any]) -> None:
    wait["held"] = False

    def other() -> None:
        wait["hub"].runs = [
            {"name": "check", "status": "in_progress", "conclusion": None},
            {"name": "lint", "status": "completed", "conclusion": "failure"},
        ]

    wait["ticks"].append((120, other))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.FULL)]


def test_a_push_to_the_head_runs_the_round_after_its_poll(wait: dict[str, Any]) -> None:
    wait["held"] = False
    wait["ticks"].append((90, lambda: setattr(wait["origin"], "head", "c" * 40)))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.QUEUE_POLL)]


def test_a_base_that_moves_before_the_first_poll_still_runs_the_round(wait: dict[str, Any]) -> None:
    """The base the round read is where the probe starts, so a merge (the PR's own, by a queue) seconds after the
    round is still a move (#1915 review)."""
    wait["held"] = False
    wait["ticks"].append((10, lambda: setattr(wait["origin"], "base", "d" * 40)))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.QUEUE_POLL)]


def test_a_required_check_that_turns_red_before_the_first_poll_runs_the_round(
    wait: dict[str, Any],
) -> None:
    wait["held"] = False

    def red() -> None:
        wait["hub"].runs = [{"name": "check", "status": "completed", "conclusion": "failure"}]

    wait["ticks"].append((10, red))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.QUEUE_POLL)]


def test_a_lock_freed_while_waiting_on_ci_runs_the_round(wait: dict[str, Any]) -> None:
    """A land that deferred to an older waiter watches the lock too, and runs its round once that waiter frees it."""
    wait["held"] = False
    wait["ticks"].append((60, wait["origin"].stamp))  # the older waiter takes it: still held
    wait["ticks"].append((150, lambda: wait["origin"].stamp(approvals.FREE)))
    approvals.land(7, wait=True)
    assert wait["rounds"][:2] == [0.0, float(approvals.QUEUE_POLL)]


def test_a_ci_probe_that_fails_runs_the_round_and_never_ends_the_wait(
    wait: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    wait["held"] = False
    origin = wait["origin"]

    def offline(*args: str) -> str:
        if args[0] == "ls-remote" and 30 <= wait["now"] < 240:
            raise subprocess.CalledProcessError(
                128, ["git"], "", "Could not resolve host: github.com"
            )
        return origin(*args)

    monkeypatch.setattr(approvals, "git", offline)
    assert approvals.land(7, wait=True) == approvals.WAITING  # to the ceiling, not a failure
    assert wait["rounds"][:2] == [0.0, float(approvals.QUEUE_POLL)]


def test_the_real_round_records_what_the_probe_watches(monkeypatch: pytest.MonkeyPatch) -> None:
    """landing() itself, its batch stubbed: the base, the named PRs and the base's required checks but the loop's own."""
    pull = {"number": 7, "headRefName": "feature", "headRefOid": HEAD, "baseRefOid": BASE_TIP}
    seen: dict[str, Any] = {}

    def batch(*_a: Any, **_k: Any) -> tuple[int, bool]:
        seen.update(
            base=approvals.watched["base"],
            pulls=approvals.watched["pulls"],
            required=set(approvals.watched["required"]),
        )
        return approvals.WAITING, True

    monkeypatch.setattr(approvals, "land_base", lambda pr: ([pull], "main", 0))
    monkeypatch.setattr(
        approvals.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
    )
    monkeypatch.setattr(approvals, "policy_from", lambda base: contextlib.nullcontext())
    monkeypatch.setattr(approvals, "project", lambda: (None, None))
    monkeypatch.setattr(approvals, "required_checks", lambda base: {"check", approvals.LAND})
    monkeypatch.setattr(approvals, "placed", lambda *a: contextlib.nullcontext())
    monkeypatch.setattr(approvals, "mergify", lambda loop: False)
    monkeypatch.setattr(approvals, "landing_here", batch)
    monkeypatch.setattr(approvals, "land_event", lambda *a, **k: None)
    assert approvals.landing(7) == (approvals.WAITING, True)
    assert seen == {"base": "main", "pulls": [pull], "required": {"check"}}
