"""approvals.py: `approve merge` and `land` where GitHub refuses the commit-status write (#1816).

A cloud session's GitHub proxy refuses `POST statuses/<sha>` with a 403 while comments, labels and the merge pass. The
go then rests on its `Approved: merge` record, which go_on reads on a head with no `owner` status when a writer wrote
it, and `land` under `land.queue: mergify` hands over with `loop:queued` and a `Queued for Mergify` record naming the
head, which the land-status workflow turns into the `land` status. Driven through main() against the fixtures of
test_approvals_mergify_queue.py, on a PR touching `.github/**`, which the fixture's risk rule makes wait for a go on its
head.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from approvals_harness import add, approvals, git_in, lands, verdict_on  # noqa: F401
from test_approvals_cloud_queue import cloud_queue  # noqa: F401
from test_approvals_github_queue import labels_of, notes_on, queue, run  # noqa: F401
from test_approvals_mergify_handover import risky
from test_approvals_mergify_queue import land_statuses, mergify  # noqa: F401

# what `gh` prints when a cloud session's proxy refuses the status write
PROXY_403 = (
    "gh: Write access to this GitHub API path is not permitted through this proxy. (HTTP 403)"
)


@pytest.fixture
def refused(
    mergify: dict[str, Any],
    hub: dict[str, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """`mergify` with `loop.delegate: all`, where every status write is refused as the proxy refuses it; `tried` holds
    each (head, context) attempted, and `hub` stays empty."""
    loop = mergify["work"] / "docs" / "agents" / "loop.md"
    loop.write_text(add(loop.read_text(), "loop", "delegate: all\n"))
    tried: list[tuple[str, str]] = []

    def post(head: str, context: str, description: str, state: str = "success") -> None:
        tried.append((head, context))
        raise subprocess.CalledProcessError(1, "gh", stderr=PROXY_403)

    monkeypatch.setattr(approvals, "post_status", post)
    mergify["tried"] = tried
    return mergify


def delegate(number: int, head: str, *more: str) -> int:
    return approvals.main(
        ["approve", "merge", str(number), "--head", head, "--by", "delegate", *more]
    )


def handed(state: dict[str, Any], number: int) -> list[str]:
    return notes_on(state, number, approvals.HANDED)


def push(state: dict[str, Any], number: int, name: str) -> str:
    """A commit on PR #number's head writing `name`, pushed as its new head with a satisfied verdict on it."""
    work, pull = state["work"], state["pulls"][number]
    git_in(work, "switch", "-q", "--detach", pull["headRefOid"])
    (work / name).parent.mkdir(parents=True, exist_ok=True)
    (work / name).write_text("changed\n")
    git_in(work, "add", name)
    git_in(work, "commit", "-q", "-m", f"PR {number} again")
    head = git_in(work, "rev-parse", "HEAD").strip()
    git_in(
        work,
        "push",
        "-q",
        "-f",
        "origin",
        f"{head}:refs/heads/pr{number}",
        f"{head}:refs/pull/{number}/head",
    )
    pull["headRefOid"] = head
    pull["reviews"]["nodes"].append(verdict_on(head))
    return head


def test_a_refused_owner_status_leaves_the_record_as_the_go(
    refused: dict[str, Any],
    hub: dict[str, list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The delegate's go with the `owner` status refused: the record names the head, `check merge` reads the go from
    it, and the hand-over that follows queues the PR by label and record, with no status written anywhere."""
    head = risky(refused, 7)
    assert delegate(7, head) == 0
    out = capsys.readouterr().out
    assert f"the `owner` status on {head} was not written, GitHub refused it" in out
    assert f"PR #7: the delegate's go is on {head}" in out
    assert (head, "owner") in refused["tried"] and hub == {}
    # the go is read from the record alone
    assert approvals.main(["check", "merge", "7"]) == 0
    assert f"PR #7: the go on {head} is the delegate's" in capsys.readouterr().out
    # and the hand-over went through on the record
    assert "loop:queued" in labels_of(refused, 7)
    [record] = handed(refused, 7)
    assert approvals.fields(record)["head"] == head


def test_land_hands_over_by_record_when_the_status_is_refused(
    refused: dict[str, Any],
    hub: dict[str, list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`land` under Mergify with the `land` status refused: `loop:queued` and one hand-over record pinned to the head;
    a second land before the workflow posts the status adds no second record."""
    head = refused["opened"](7)
    code, lines = refused["land"]("7")
    assert code == 0, lines
    assert lines[-1] == f"PR #7 queued for Mergify at {head}"
    assert (head, "land") in refused["tried"] and land_statuses(hub, head) == []
    assert "loop:queued" in labels_of(refused, 7)
    [record] = handed(refused, 7)
    assert record.splitlines()[0] == approvals.HANDED
    assert approvals.fields(record)["head"] == head
    code, lines = refused["land"]("7")
    assert code == 0, lines
    assert f"PR #7: its hand-over record for {head} is already on the PR" in lines
    assert len(handed(refused, 7)) == 1


def test_a_record_go_on_a_stale_head_is_refused(
    refused: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """A go recorded on one head carries nothing to a head with a change of its own: `check merge` and `land` wait for
    a go on the new head, and nothing is handed over for it."""
    old = risky(refused, 7)
    assert delegate(7, old) == 0
    refused["pulls"][7]["labels"]["nodes"] = [
        each for each in refused["pulls"][7]["labels"]["nodes"] if each["name"] != "loop:queued"
    ]
    new = push(refused, 7, ".github/y.txt")
    capsys.readouterr()
    assert approvals.main(["check", "merge", "7"]) == 3
    out = capsys.readouterr().out
    assert "waits for the owner's go on its head" in out and f"--head {new}" in out
    code, lines = refused["land"]("7")
    assert code == 3, lines
    assert "loop:queued" not in labels_of(refused, 7)
    assert [approvals.fields(each)["head"] for each in handed(refused, 7)] == [old]
    # the go is refused on the old head too, since the PR's head moved
    assert delegate(7, old) == 1


def test_a_record_by_a_stranger_is_no_go(
    refused: dict[str, Any], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A comment is anyone's to write on a public repo: a merge record by an account that can't write is no go."""
    monkeypatch.setattr(approvals, "writer", lambda login: login == "loop")
    head = risky(refused, 7)
    note = approvals.fold(
        approvals.VOICED["delegate"],
        f"Go to merge {head[:7]}.",
        f"Approved: merge\nBy: delegate\nHead: {head}",
    )
    refused["pulls"][7]["comments"]["nodes"].append(
        {
            "id": "IC_stranger",
            "author": {"login": "stranger"},
            "body": note,
            "createdAt": "2026-01-01T00:00:00Z",
            "lastEditedAt": None,
            "isMinimized": False,
            "viewerCanMinimize": False,
        }
    )
    capsys.readouterr()
    assert approvals.main(["check", "merge", "7"]) == 3
    assert "waits for the owner's go on its head" in capsys.readouterr().out


def test_a_withdrawal_record_takes_the_go_back(
    refused: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """With the statuses refused, the newer `Withdrawn: merge` record on the head withdraws the go its record gave."""
    head = risky(refused, 7)
    assert delegate(7, head) == 0
    assert approvals.main(["check", "merge", "7"]) == 0
    assert delegate(7, head, "--withdraw") == 0
    assert (head, "owner") in refused["tried"][1:]
    capsys.readouterr()
    assert approvals.main(["check", "merge", "7"]) == 3
    assert "waits for the owner's go on its head" in capsys.readouterr().out


def test_a_status_on_the_head_still_decides_alone(
    refused: dict[str, Any],
    hub: dict[str, list[dict[str, Any]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An `owner` status written where statuses could be (a host) decides over any record: a failing one withdraws
    the go the record gave."""
    head = risky(refused, 7)
    assert delegate(7, head) == 0
    hub[head] = [
        {
            "context": "owner",
            "state": "failure",
            "description": f"The delegate withdrew their go on {head[:12]}",
            "creator": {"login": "loop"},
        }
    ]
    capsys.readouterr()
    assert approvals.main(["check", "merge", "7"]) == 3
    assert "waits for the owner's go on its head" in capsys.readouterr().out


def test_another_status_failure_still_stops(
    mergify: dict[str, Any],
    hub: dict[str, list[dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure that is no refusal (GitHub unreachable) stops the go as before, recording nothing."""

    def down(head: str, context: str, description: str, state: str = "success") -> None:
        raise subprocess.CalledProcessError(1, "gh", stderr="gh: connection reset")

    monkeypatch.setattr(approvals, "post_status", down)
    head = risky(mergify, 7)
    assert approvals.main(["approve", "merge", "7", "--head", head, "--by", "owner"]) != 0
    assert not notes_on(mergify, 7, approvals.VOICED["owner"])
