"""`land --wait` waits out a GitHub rate limit and polls a held lock without GitHub calls (#1209)."""

from __future__ import annotations

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
    assert 100 < calls["sleeps"][0] <= 125


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
    assert calls["sleeps"] == [60, 120]


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
