"""approvals.py: `land` through a Mergify merge queue, `land.queue: mergify` (#1658).

`land` judges each candidate as for any queue, then hands it to Mergify with the `land` status on its head and the
`loop:queued` label, which `.mergify.yml`'s queue conditions read; it takes no lock, runs no gate and merges nothing.
Driven end to end against the `queue` fake GitHub (test_approvals_github_queue.py) on a base whose rules require
`qualify` and no GitHub merge queue, asserting on what GitHub sees: statuses, labels, comments and draft state.
"""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    add,
    approvals,
    git_in,
    lands,  # noqa: F401
    verdict_on,
)
from test_approvals_cloud_queue import cloud_queue  # noqa: F401
from test_approvals_github_queue import labels_of, notes_on, queue, run  # noqa: F401


@pytest.fixture
def mergify(queue: dict[str, Any]) -> dict[str, Any]:
    """`queue` on a base whose rules require `qualify` and no GitHub merge queue, the policy naming Mergify."""
    queue["rules"] = approvals.github.Required({"qualify"})
    loop = queue["work"] / "docs" / "agents" / "loop.md"
    loop.write_text(add(loop.read_text(), "land", "queue: mergify\n"))
    return queue


def land_statuses(hub: dict[str, list[dict[str, Any]]], head: str) -> list[tuple[str, str]]:
    """The `land` statuses on `head`, newest first, as (state, description)."""
    return [
        (each["state"], each["description"])
        for each in hub.get(head, [])
        if each["context"] == "land"
    ]


def untouched(state: dict[str, Any]) -> None:
    """No landing lock, no local gate, no merge by land itself and nothing in GitHub's queue."""
    assert (state["tips"](), state["runs"](), state["merged"](), state["enqueued"]) == (
        [],
        0,
        [],
        [],
    )


def test_land_queues_for_mergify(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    head = mergify["opened"](7)
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    assert lines[-1] == f"PR #7 queued for Mergify at {head}"
    assert land_statuses(hub, head) == [("success", f"Queued for Mergify at {head}")]
    assert "loop:queued" in labels_of(mergify, 7)
    untouched(mergify)


def test_a_pr_body_loses_its_session_link_before_it_is_handed_to_mergify(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    """Mergify squashes from the PR's title and body, so land drops a cloud session's link line from it first."""
    body = "## Summary\n\nFix it.\n\n## Evidence\n\nlog line"
    head = mergify["opened"](7, body=f"{body}\n\nhttps://claude.ai/code/session_01AbCdEf\n")
    mergify["pulls"][7]["viewerCanUpdate"] = True
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    assert mergify["edits"] == {"repos/{owner}/{repo}/pulls/7": body}
    assert land_statuses(hub, head) == [("success", f"Queued for Mergify at {head}")]


def test_land_queues_only_candidates(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    """A PR with no verdict, or with `qualify` red, is no candidate (exit 1); one whose `qualify` runs waits (3)."""
    unproven = mergify["open"](7, {"7.txt": "7\n"}, checks=(("qualify", "SUCCESS"),), reviews=())
    red = mergify["open"](8, {"8.txt": "8\n"}, checks=(("qualify", "FAILURE"),))
    running = mergify["open"](9, {"9.txt": "9\n"}, checks=(("qualify", None),))
    for number, head, code in ((7, unproven, 1), (8, red, 1), (9, running, 3)):
        got, lines = mergify["land"](str(number))
        assert got == code, lines
        assert land_statuses(hub, head) == []
        assert "loop:queued" not in labels_of(mergify, number)
    untouched(mergify)


def test_land_leaves_a_queued_pr(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    head = mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    assert lines[-1] == f"PR #7 is queued for Mergify at {head}"
    assert len(land_statuses(hub, head)) == 1


def test_a_push_after_queueing_queues_the_new_head(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    """The `land` status binds the hand-over to one head: a new head carries none, so land queues it anew."""
    first = mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    work = mergify["work"]
    (work / "7.txt").write_text("7 again\n")
    git_in(work, "commit", "-q", "-am", "PR 7 again")
    second = git_in(work, "rev-parse", "HEAD").strip()
    git_in(work, "push", "-q", "origin", f"{second}:refs/heads/pr7", f"{second}:refs/pull/7/head")
    mergify["pulls"][7].update(headRefOid=second, reviews={"nodes": [verdict_on(second)]})
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    assert lines[-1] == f"PR #7 queued for Mergify at {second}"
    assert land_statuses(hub, second) == [("success", f"Queued for Mergify at {second}")]
    assert land_statuses(hub, first) == [("success", f"Queued for Mergify at {first}")]


def test_land_evicts_a_dequeued_pr(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    head = mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    # Mergify dequeued it after its retry, labelling it, and says why on its queue check run; a green check isn't it
    mergify["pulls"][7]["labels"]["nodes"].append({"name": "loop:dequeued"})
    failed = run("Mergify Merge Queue", "failure", 551)
    failed["output"] = {"title": "The pull request has been removed from the queue `default`"}
    mergify["checks"][head] = [run("qualify", "success", 550), failed]
    code, lines = mergify["land"]("7")
    assert code == 1, lines
    assert f"PR #7 was dequeued by Mergify at {head}: evicted" in lines
    assert land_statuses(hub, head)[0] == ("error", "Evicted from the Mergify merge queue")
    assert labels_of(mergify, 7) & {"loop:queued", "loop:dequeued"} == set()
    assert mergify["pulls"][7]["isDraft"] is True
    [body] = notes_on(mergify, 7, "Evicted from the merge queue")
    assert "The pull request has been removed from the queue `default`" in body
    assert f"Head: {head}" in body
    untouched(mergify)


def test_a_dequeued_label_from_an_older_head_comes_off_and_the_pr_is_queued(
    mergify: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    head = mergify["opened"](7)
    mergify["pulls"][7]["labels"]["nodes"].append({"name": "loop:dequeued"})
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    assert "loop:dequeued" not in labels_of(mergify, 7)
    assert land_statuses(hub, head) == [("success", f"Queued for Mergify at {head}")]
    assert mergify["pulls"][7]["isDraft"] is False


def test_bare_land_writes_the_trail(mergify: dict[str, Any]) -> None:
    """Mergify merged #7, which land had queued: a bare land comments `Landed` and takes the label off."""
    mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    approvals.github.gh(
        "pr", "merge", "7", "--squash", "--match-head-commit", mergify["pulls"][7]["headRefOid"]
    )
    commit = mergify["squashes"][7]
    mergify["checks"][commit] = [run("qualify", "success", 991)]
    code, lines = mergify["land"]()
    assert code == 0, lines
    [body] = notes_on(mergify, 7, "Landed")
    tree = approvals.github.commit_tree(commit)
    assert f"Base: {commit}" in body and f"Tree: {tree}" in body
    assert "Gate: Mergify merge queue, https://github.com/o/r/actions/runs/99" in body
    assert "loop:queued" not in labels_of(mergify, 7)
    # written once
    assert mergify["land"]()[0] == 0
    assert len(notes_on(mergify, 7, "Landed")) == 1


def test_cloud_land_queues_for_mergify(
    cloud_queue: dict[str, Any],
    hub: dict[str, list[dict[str, Any]]],
) -> None:
    """In a cloud session with no signing key, the Mergify path queues over REST; the local path still refuses."""
    cloud_queue["rules"] = approvals.github.Required({"qualify"})
    head = cloud_queue["opened"](7)
    code, lines = cloud_queue["land"]("7")
    assert code == 1 and any("land in a cloud session needs" in line for line in lines), lines
    loop = cloud_queue["work"] / "docs" / "agents" / "loop.md"
    loop.write_text(add(loop.read_text(), "land", "queue: mergify\n"))
    code, lines = cloud_queue["land"]("7")
    assert code == 0, lines
    assert land_statuses(hub, head) == [("success", f"Queued for Mergify at {head}")]
    assert "loop:queued" in labels_of(cloud_queue, 7)
    assert cloud_queue["graphql"] == []
    untouched(cloud_queue)


def test_mergify_refuses_signed_squash(mergify: dict[str, Any]) -> None:
    mergify["opened"](7)
    loop = mergify["work"] / "docs" / "agents" / "loop.md"
    loop.write_text(
        add(loop.read_text(), "land", "signed_squash_to: main\nallowed_signers: signers\n")
    )
    code, lines = mergify["land"]("7")
    assert code == 1
    assert any(
        "`land.queue: mergify`" in line and "`land.signed_squash_to`" in line for line in lines
    ), lines
    untouched(mergify)


def test_an_unknown_queue_is_refused(mergify: dict[str, Any]) -> None:
    mergify["opened"](7)
    loop = mergify["work"] / "docs" / "agents" / "loop.md"
    loop.write_text(loop.read_text().replace("queue: mergify", "queue: bors"))
    code, lines = mergify["land"]("7")
    assert code == 1 and any("land.queue" in line for line in lines), lines
