"""approvals.py: a queue red on a diff no test can reach is retried, never counted against the head (#2146).

The reach is the project's own `select` cut (`selected`, the one `affected-tests` runs by): no build input and no
`select.checks` command among the changed files. A red on a diff that reaches a test counts as before.
"""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import approvals, lands  # noqa: F401
from test_approvals_github_queue import (  # noqa: F401
    AGAIN_AT,
    RED_AT,
    notes_on,
    queue,
    red_group,
)
from test_approvals_mergify_queue import mergify, run  # noqa: F401
from test_approvals_mergify_solo import labels_of


def cut(monkeypatch: pytest.MonkeyPatch, inputs: list[str], commands: list[str]) -> None:
    monkeypatch.setattr(approvals, "merge_base_of", lambda base, head: "b")
    monkeypatch.setattr(approvals, "selected", lambda base, head=None: (inputs, commands))


def two_reds(queue: dict[str, Any]) -> tuple[int, list[str]]:
    queue["opened"](7)
    queue["remove"](7, approvals.FAILED_CHECKS, at=RED_AT, group="g1")
    red_group(queue, "g1", 410)
    queue["land"]("7")
    queue["remove"](7, approvals.FAILED_CHECKS, at=AGAIN_AT, group="g2")
    red_group(queue, "g2", 420)
    return queue["land"]("7")


def test_a_second_red_on_a_diff_no_test_reaches_leaves_the_pr_ready_and_retries_it(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    cut(monkeypatch, [], [])
    code, lines = two_reds(queue)
    assert code == 0, lines
    assert any("no path it changes can reach a test" in line for line in lines)
    assert not queue["pulls"][7]["isDraft"]
    assert len(queue["enqueued"]) == 2  # enqueued again after each red
    assert not notes_on(queue, 7, approvals.QUEUE_EVICTED)


def test_a_second_red_on_a_diff_that_reaches_a_test_still_turns_the_pr_to_draft(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    cut(monkeypatch, ["src/app.py"], [])
    code, lines = two_reds(queue)
    assert code == 1, lines
    assert queue["pulls"][7]["isDraft"]


def test_a_diff_that_reaches_a_select_check_counts_its_red(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    cut(monkeypatch, [], ["mise run check:ci"])
    code, _ = two_reds(queue)
    assert code == 1


def test_a_project_with_no_select_counts_every_red(queue: dict[str, Any]) -> None:
    code, _ = two_reds(queue)
    assert code == 1


def test_an_unreachable_red_that_keeps_coming_counts_past_the_retries(
    queue: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    cut(monkeypatch, [], [])
    queue["opened"](7)
    for index in range(approvals.UNREACHABLE_RETRIES + 2):
        queue["remove"](
            7, approvals.FAILED_CHECKS, at=f"2026-10-02T1{index}:00:00Z", group=f"g{index}"
        )
        red_group(queue, f"g{index}", 400 + index * 10)
        code, lines = queue["land"]("7")
        if code == 1:
            break
    # three retried for nothing, the fourth red counts once, the fifth is the second counted one
    assert (code, index) == (1, approvals.UNREACHABLE_RETRIES + 1), lines
    assert queue["pulls"][7]["isDraft"]


def test_a_ci_only_diff_selects_no_product_test() -> None:
    """The cut a pre-push hook gets from `affected-tests`: CI workflows, CI scripts and agent docs are no build input."""
    select = {
        "build_inputs": ["pyproject.toml"],
        "non_product": [".github/**", "docs/agents/**", "tools/ci/**"],
        "checks": [{"paths": ["tools/ci/**"], "command": "pytest tools/ci"}],
    }
    files = [".github/workflows/ci.yml", "docs/agents/roles.md", "tools/ci/run.py"]
    assert approvals.classify(files, select) == ([], ["pytest tools/ci"])
    assert approvals.classify([*files, "src/app.py"], select)[0] == ["src/app.py"]


def dequeued(mergify: dict[str, Any], head: str) -> tuple[int, list[str]]:
    mergify["pulls"][7]["labels"]["nodes"].append({"name": "loop:dequeued"})
    failed = run("Mergify Merge Queue", "failure", 551)
    failed["output"] = {"title": "The pull request has been removed from the queue `default`"}
    mergify["checks"][head] = [run("qualify", "success", 550), failed]
    return mergify["land"]("7")


def test_a_mergify_dequeue_on_a_diff_no_test_reaches_is_queued_again_not_evicted(
    mergify: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    cut(monkeypatch, [], [])
    code, lines = dequeued(mergify, head)
    assert code == 0, lines
    assert any("no path it changes can reach a test: queued again" in line for line in lines)
    assert not mergify["pulls"][7]["isDraft"]
    assert approvals.REQUEUE in [body.strip() for _, body in mergify["raw"]]
    [record] = notes_on(mergify, 7, approvals.UNREACHABLE_RED)
    assert f"Head: {head}" in record
    assert "loop:dequeued" not in labels_of(mergify, 7)


def test_a_mergify_dequeue_on_a_diff_that_reaches_a_test_is_evicted(
    mergify: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    head = mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    cut(monkeypatch, ["src/app.py"], [])
    code, lines = dequeued(mergify, head)
    assert code == 1, lines
    assert mergify["pulls"][7]["isDraft"]


def test_a_mergify_unreachable_retry_count_starts_anew_when_the_pr_is_ready_again() -> None:
    head = "h"
    body = f"{approvals.UNREACHABLE_RED}\n\nHead: {head}"
    pull = {
        "headRefOid": head,
        "baseRefName": "main",
        "comments": {
            "nodes": [
                {"body": body, "createdAt": f"2026-10-02T0{i}:00:00Z", "author": {"login": "x"}}
                for i in range(approvals.UNREACHABLE_RETRIES)
            ]
        },
        "timelineItems": {"nodes": []},
    }
    with pytest.MonkeyPatch.context() as patch:
        cut(patch, [], [])
        patch.setattr(approvals, "fetched", lambda sha: True)
        assert not approvals.unreachable_dequeue(pull)
        pull["timelineItems"]["nodes"].append(
            {"__typename": "ReadyForReviewEvent", "createdAt": "2026-10-02T09:00:00Z"}
        )
        assert approvals.unreachable_dequeue(pull)
