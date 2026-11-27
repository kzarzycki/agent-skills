"""approvals.py: a Mergify hand-over GitHub answers with a 5xx is tried again, then fails `land` (#2405, #1226).

`land --only --wait` under `land.queue: mergify` exits 0 only once the PR is queued: a hand-over call that answers
HTTP 500 is retried after a short wait, and one that never succeeds ends `land` with exit 1 and one line naming the
error. Driven against the fixtures of test_approvals_mergify_queue.py; `time.sleep` is faked, so no test waits.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from approvals_harness import approvals, lands  # noqa: F401
from test_approvals_cloud_queue import cloud_queue  # noqa: F401
from test_approvals_github_queue import labels_of, queue, run  # noqa: F401
from test_approvals_mergify_queue import land_statuses, mergify  # noqa: F401

DOWN = "gh: Server Error (HTTP 500)"


def answering_500(monkeypatch: pytest.MonkeyPatch, times: int) -> tuple[list[int], list[int]]:
    """`post_status` (the hand-over call) answers HTTP 500 `times` times, then works; returns its call count and
    the waits slept."""
    calls: list[int] = []
    slept: list[int] = []
    post = approvals.post_status

    def status(*args: Any, **kwargs: Any) -> None:
        calls.append(1)
        if len(calls) <= times:
            raise approvals.subprocess.CalledProcessError(1, "gh", stderr=DOWN)
        post(*args, **kwargs)

    monkeypatch.setattr(approvals, "post_status", status)
    monkeypatch.setattr(
        time, "sleep", lambda seconds: slept.append(seconds) if seconds >= 1 else None
    )
    return calls, slept


def test_a_hand_over_that_never_succeeds_exits_non_zero_and_names_the_error(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = mergify["opened"](7)
    calls, slept = answering_500(monkeypatch, times=99)
    code, lines = mergify["land"]("7", "--only", "--wait")
    assert code == 1, lines
    refused = [line for line in lines if "refused its hand-over" in line]
    assert len(refused) == 1 and DOWN in refused[0] and refused[0].endswith("not queued, exit 1"), (
        lines
    )
    assert len(calls) == len(approvals.HAND_OVER_BACKOFF) + 1
    assert slept == list(approvals.HAND_OVER_BACKOFF)
    assert land_statuses(hub, head) == [] and "loop:queued" not in labels_of(mergify, 7)


def test_a_hand_over_answered_500_once_is_tried_again_and_queued(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = mergify["opened"](7)
    calls, slept = answering_500(monkeypatch, times=1)
    code, lines = mergify["land"]("7", "--only")
    assert code == 0, lines
    assert lines[-1] == f"PR #7 queued for Mergify at {head}"
    assert (len(calls), slept) == (2, [approvals.HAND_OVER_BACKOFF[0]])
    assert land_statuses(hub, head) == [("success", f"Queued for Mergify at {head}")]
    assert "loop:queued" in labels_of(mergify, 7)
