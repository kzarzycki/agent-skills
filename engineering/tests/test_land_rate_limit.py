"""`land --wait` waits out a GitHub rate limit and polls a held lock without GitHub calls (#1209)."""

from __future__ import annotations

import itertools
import subprocess
import time
from typing import Any

import pytest
from approvals_harness import approvals

github = approvals.github
real_poll_seconds = approvals.poll_seconds


def refuse(stderr: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["gh"], "", stderr)


@pytest.fixture(autouse=True)
def poll_unstretched(monkeypatch: pytest.MonkeyPatch) -> None:
    """The quota read is a `gh` call: tests of the wait loop poll at POLL without it."""
    monkeypatch.setattr(approvals, "poll_seconds", lambda: approvals.POLL)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """gh answers the scripted `replies` in order (an exception is raised); sleeps are recorded, not taken."""
    seen: dict[str, Any] = {"gh": [], "sleeps": [], "replies": []}

    def run(cmd: list[str], **kw: Any) -> Any:
        seen["gh"].append(cmd)
        if cmd[:3] == ["gh", "api", "rate_limit"]:
            return subprocess.CompletedProcess(cmd, 0, str(int(time.time()) + 120), "")
        reply = seen["replies"].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return subprocess.CompletedProcess(cmd, 0, reply, "")

    monkeypatch.setattr(github.subprocess, "run", run)
    monkeypatch.setattr(github.time, "sleep", seen["sleeps"].append)
    monkeypatch.setattr(github.random, "randint", lambda low, high: 0)
    monkeypatch.setattr(github, "wait_until", time.monotonic() + 3600)
    return seen


def test_a_primary_limit_waits_for_the_reset_then_carries_on(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse("gh: API rate limit exceeded (HTTP 403)"), "ok"]
    assert github.gh("api", "x") == "ok"
    assert 100 < sum(calls["sleeps"]) <= 125 and max(calls["sleeps"]) <= 60


def test_a_secondary_limit_waits_for_retry_after(calls: dict[str, Any]) -> None:
    calls["replies"] = [
        refuse("You have exceeded a secondary rate limit (HTTP 403) Retry-After: 17"),
        "ok",
    ]
    assert github.gh("api", "x") == "ok"
    assert calls["sleeps"] == [17]


def test_a_secondary_limit_without_retry_after_backs_off_from_60(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse("secondary rate limit (HTTP 403)")] * 2 + ["ok"]
    assert github.gh("api", "x") == "ok"
    assert calls["sleeps"] == [60, 60, 60]


def test_another_403_fails_at_once(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse("Resource not accessible by integration (HTTP 403)")]
    with pytest.raises(subprocess.CalledProcessError):
        github.gh("api", "x")
    assert calls["sleeps"] == []


def test_without_wait_a_limit_fails_naming_the_reset(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(github, "wait_until", None)
    calls["replies"] = [refuse("API rate limit exceeded (HTTP 403)")]
    with pytest.raises(subprocess.CalledProcessError) as failed:
        github.gh("api", "x")
    assert "rate limit, resets at" in failed.value.stderr
    assert calls["sleeps"] == []


def test_a_limit_past_the_ceiling_fails(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(github, "wait_until", time.monotonic() + 5)
    calls["replies"] = [refuse("API rate limit exceeded (HTTP 403)")]
    with pytest.raises(subprocess.CalledProcessError):
        github.gh("api", "x")


def test_a_held_lock_at_an_unchanged_tip_is_polled_without_gh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran, listed = [], []

    def landing(pr: Any, only: bool = False) -> tuple[int, bool]:
        ran.append(1)
        approvals.held_tip = ("refs/heads/loop-landing/main", "abc")
        return approvals.WAITING, True

    def git(*args: str) -> str:
        listed.append(args)
        return "abc\trefs/heads/loop-landing/main\n"

    monkeypatch.setattr(approvals, "landing", landing)
    monkeypatch.setattr(approvals, "git", git)
    monkeypatch.setattr(approvals, "POLL", 0.01)
    monkeypatch.setattr(approvals, "CEILING", 1)
    monkeypatch.setattr(approvals, "RECHECK", 0.3)
    assert approvals.land(1, wait=True) == approvals.WAITING
    assert 1 <= len(ran) <= 6  # one landing() per RECHECK, not one per 0.01 s poll
    assert len(listed) > len(ran) * 3


def test_land_wait_turns_the_rate_limit_wait_on_and_sleeps_in_printing_slices(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(github, "wait_until", None)  # land() alone sets it
    calls["replies"] = [refuse("secondary rate limit (HTTP 403) Retry-After: 150"), "ok"]
    monkeypatch.setattr(
        approvals, "landing", lambda pr, only=False: (int(github.gh("api", "x") != "ok"), False)
    )
    assert approvals.land(1, wait=True) == 0
    assert calls["sleeps"] == [60, 60, 30]  # none of them silent past wait-for's 300 s
    assert capsys.readouterr().err.count("GitHub rate limit, waiting until") == 3


@pytest.mark.parametrize(
    "message", ["API rate limit exceeded (HTTP 403)", "gh: API rate limit exceeded for user ID 1."]
)
def test_a_graphql_limit_waits_for_the_graphql_reset(calls: dict[str, Any], message: str) -> None:
    calls["replies"] = [refuse(message), "ok"]
    github.gh("api", "graphql", "-f", "query=x")
    assert ["gh", "api", "rate_limit", "--jq", ".resources.graphql.reset"] in calls["gh"]


def test_a_held_lock_is_asked_of_github_again_after_recheck_and_said_each_minute(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    now, ran = [0.0], []
    monkeypatch.setattr(github, "wait_until", None)
    monkeypatch.setattr(approvals.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        approvals.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds)
    )

    def landing(pr: Any, only: bool = False) -> tuple[int, bool]:
        ran.append(now[0])
        approvals.held_tip = ("refs/heads/loop-landing/main", "abc")
        print("another land holds the landing lock")
        return approvals.WAITING, True

    monkeypatch.setattr(approvals, "landing", landing)
    monkeypatch.setattr(approvals, "git", lambda *a: "abc\trefs/heads/loop-landing/main\n")
    assert approvals.land(1, wait=True) == approvals.WAITING
    assert all(b - a == approvals.RECHECK for a, b in itertools.pairwise(ran))
    assert len(ran) > 2
    # the log is never silent for wait-for's 300 s: the held state is said again every SLOT_SAY_SECONDS
    assert capsys.readouterr().out.count("another land holds") >= approvals.CEILING // 120


def test_a_round_that_does_not_hold_the_lock_polls_no_stale_tip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rounds, listed = [], []
    monkeypatch.setattr(github, "wait_until", None)
    monkeypatch.setattr(approvals, "POLL", 0.01)
    monkeypatch.setattr(approvals, "RECHECK", 0.05)

    def landing(pr: Any, only: bool = False) -> tuple[int, bool]:
        rounds.append(len(listed))
        if len(rounds) == 1:
            approvals.held_tip = (
                "refs/heads/loop-landing/main",
                "abc",
            )  # held; the next round is not
        return (approvals.WAITING, len(rounds) < 3)

    monkeypatch.setattr(approvals, "landing", landing)
    monkeypatch.setattr(approvals, "git", lambda *a: listed.append(a) or "abc\trefs\n")
    approvals.land(1, wait=True)
    assert rounds[2] == rounds[1]  # round 2 held no lock, so nothing was listed after it


def test_a_rest_limit_message_without_a_status_is_not_a_limit(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse("gh: API rate limit exceeded for user ID 1.")]
    with pytest.raises(subprocess.CalledProcessError):
        github.gh("api", "repos/x")
    assert calls["sleeps"] == []


def test_a_rate_limit_wait_adds_bounded_jitter(
    calls: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = []
    monkeypatch.setattr(
        github.random, "randint", lambda low, high: seen.append((low, high)) or high
    )
    calls["replies"] = [refuse("secondary rate limit (HTTP 403) Retry-After: 30"), "ok"]
    github.gh("api", "x")
    assert seen == [(0, github.JITTER)]
    assert sum(calls["sleeps"]) == 30 + github.JITTER


@pytest.mark.parametrize(("answer", "poll"), [("400 5000", 300), ("500 5000", 30), ("x", 30)])
def test_a_low_quota_stretches_the_poll(
    monkeypatch: pytest.MonkeyPatch, answer: str, poll: int
) -> None:
    monkeypatch.setattr(github, "gh", lambda *args: answer)
    assert real_poll_seconds() == poll


def test_a_low_quota_poll_still_says_the_wait_each_minute_and_asks_github_each_poll(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    now, ran = [0.0], []
    monkeypatch.setattr(github, "wait_until", None)
    monkeypatch.setattr(approvals, "poll_seconds", lambda: approvals.LOW_POLL)
    monkeypatch.setattr(approvals.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        approvals.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds)
    )

    def landing(pr: Any, only: bool = False) -> tuple[int, bool]:
        ran.append(now[0])
        print("checks pending")
        return approvals.WAITING, True

    monkeypatch.setattr(approvals, "landing", landing)
    approvals.land(1, wait=True)
    assert all(b - a == approvals.LOW_POLL for a, b in itertools.pairwise(ran))
    # said again each SLOT_SAY_SECONDS, so wait-for's 300 s stall check never fires
    assert capsys.readouterr().out.count("checks pending") >= approvals.CEILING // 120


def test_a_failed_quota_read_keeps_the_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*args: str) -> str:
        raise subprocess.CalledProcessError(1, ["gh"], "", "HTTP 502")

    monkeypatch.setattr(github, "gh", failing)
    assert real_poll_seconds() == approvals.POLL
