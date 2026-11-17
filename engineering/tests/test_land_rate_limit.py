"""`land --wait` waits out a GitHub rate limit and polls a held lock without GitHub calls (#1209)."""

from __future__ import annotations

import itertools
import subprocess
import time
from typing import Any

import pytest
from approvals_harness import approvals

github = approvals.github


def refuse(stderr: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["gh"], "", stderr)


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


def test_a_graphql_limit_waits_for_the_graphql_reset(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse("API rate limit exceeded (HTTP 403)"), "ok"]
    github.gh("api", "graphql", "-f", "query=x")
    assert ["gh", "api", "rate_limit", "--jq", ".resources.graphql.reset"] in calls["gh"]


def test_a_held_lock_is_asked_of_github_again_after_recheck_and_said_each_minute(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    now, ran = [0.0], []
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
