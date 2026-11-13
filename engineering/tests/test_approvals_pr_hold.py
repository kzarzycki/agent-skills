"""approvals.py: `needs-owner` on the PR itself holds it from `land`, and the owner's go lifts it (#968)."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pull,
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

HELD = "#7 waits for the owner (needs-owner)"


def test_a_ready_pr_carrying_needs_owner_is_no_candidate_for_land_and_check_merge_says_why(
    lands: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    lands["open"](7, {"7.txt": "7\n"}, labels=("needs-owner",))
    lands["open"](8, {"8.txt": "8\n"})
    # the batch: another PR's land takes #8 and leaves the held #7
    code, lines = lands["land"]("8")
    assert code == 0, lines
    assert HELD in lines
    assert lands["merged"]() == ["8"]
    # `--only` on the held PR itself lands nothing
    code, lines = lands["land"]("7", "--only")
    assert code == 1
    assert HELD in lines
    assert lands["merged"]() == ["8"]
    # check merge names why
    assert approvals.main(["check", "merge", "7"]) == 1
    assert HELD in capsys.readouterr().out.splitlines()


def test_the_owners_go_removes_needs_owner_from_the_pr_and_land_takes_it_again(
    lands: dict[str, Any],
    added: list[tuple[int, str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    head = lands["open"](7, {"7.txt": "7\n"}, labels=("needs-owner",))
    pr = lands["pulls"][7]

    def label(number: int, name: str, add: bool) -> None:
        added.append((number, name, add))
        held = lands["pulls"][number]["labels"]["nodes"]
        held[:] = [node for node in held if node["name"] != name] + (
            [{"name": name}] if add else []
        )

    monkeypatch.setattr(approvals, "label", label)
    assert approvals.main(["approve", "merge", "7", "--head", head, "--by", "owner"]) == 0
    assert (7, "needs-owner", False) in added
    assert "needs-owner" not in approvals.names(pr)
    code, lines = lands["land"]("7", "--only")
    assert code == 0, lines
    assert HELD not in lines
    assert lands["merged"]() == ["7"]


def test_the_delegates_go_leaves_needs_owner_on_the_pr(
    added: list[tuple[int, str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Into a feature branch, where the delegate's go is a go: the hold is still the owner's to lift."""
    pr = pull(labels=("needs-owner",))
    pr["baseRefName"] = "feature-base"
    monkeypatch.setattr(approvals, "pull_request", lambda _n: pr)
    monkeypatch.setattr(approvals, "comment", lambda _n, _body: None)
    assert approvals.main(["approve", "merge", "7", "--head", HEAD, "--by", "delegate"]) == 0
    assert (7, "needs-owner", False) not in added
