"""A rate-limit refusal GitHub words `already exceeded`, from gh api and gh pr, waits by its bucket (#1266)."""

from __future__ import annotations

import subprocess
import time
from typing import Any

import pytest
from approvals_harness import approvals

github = approvals.github
ALREADY = "gh: API rate limit already exceeded for user ID 1."
GRAPHQL = "GraphQL: API rate limit already exceeded for user ID 1."


def refuse(stderr: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["gh"], "", stderr)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """gh answers `replies` in order; `bucket` is what `gh api rate_limit` says; sleeps are recorded, not taken."""
    seen: dict[str, Any] = {"gh": [], "sleeps": [], "replies": [], "bucket": "0"}

    def run(cmd: list[str], **kw: Any) -> Any:
        seen["gh"].append(cmd)
        if cmd[:3] == ["gh", "api", "rate_limit"]:
            return subprocess.CompletedProcess(
                cmd, 0, f"{seen['bucket']} {int(time.time()) + 120}", ""
            )
        reply = seen["replies"].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return subprocess.CompletedProcess(cmd, 0, reply, "")

    monkeypatch.setattr(github.subprocess, "run", run)
    monkeypatch.setattr(github.time, "sleep", seen["sleeps"].append)
    monkeypatch.setattr(github, "wait_until", time.monotonic() + 3600)
    return seen


@pytest.mark.parametrize(
    "args,message",
    [
        (("api", "graphql", "-f", "query=x"), ALREADY),
        (("pr", "view", "1"), GRAPHQL),
        (("api", "repos/x"), ALREADY),
    ],
)
def test_already_exceeded_waits_instead_of_raising(
    calls: dict[str, Any], args: tuple[str, ...], message: str
) -> None:
    calls["replies"] = [refuse(message), "ok"]
    assert github.gh(*args) == "ok"
    assert calls["sleeps"]


def test_a_graphql_error_from_gh_pr_reads_the_graphql_bucket(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse(GRAPHQL), "ok"]
    github.gh("pr", "view", "1")
    assert any(".resources.graphql" in cmd[-1] for cmd in calls["gh"] if "rate_limit" in cmd)


def test_a_rest_refusal_reads_the_core_bucket(calls: dict[str, Any]) -> None:
    calls["replies"] = [refuse(ALREADY), "ok"]
    github.gh("api", "repos/x")
    assert any(".resources.core" in cmd[-1] for cmd in calls["gh"] if "rate_limit" in cmd)


def test_a_bucket_with_calls_left_waits_backoff_doubling(calls: dict[str, Any]) -> None:
    calls["bucket"] = "3600"
    calls["replies"] = [refuse(GRAPHQL), refuse(GRAPHQL), "ok"]
    assert github.gh("pr", "view", "1") == "ok"
    assert sum(calls["sleeps"]) == 60 + 120


def test_an_empty_bucket_waits_for_its_reset(calls: dict[str, Any]) -> None:
    calls["bucket"] = "0"
    calls["replies"] = [refuse(GRAPHQL), "ok"]
    github.gh("pr", "view", "1")
    assert 100 < sum(calls["sleeps"]) <= 125


def test_a_refusal_waits_even_where_gh_cannot_read_the_bucket() -> None:
    assert github.rate_limited(ALREADY, 60) is not None


def test_another_error_is_no_rate_limit() -> None:
    assert github.rate_limited("GraphQL: Could not resolve to a PullRequest", 60) is None


def test_a_wait_polls_the_queue_every_two_minutes_not_thirty() -> None:
    assert approvals.QUEUE_POLL == 120 and approvals.POLL == 30
