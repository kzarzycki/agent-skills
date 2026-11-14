"""approvals.py: `land` readies each named draft before it waits for the lock, and takes several PRs (#969)."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

REF = approvals.LOCK.format("main")


def lock(lands: dict[str, Any], title: str) -> None:
    """Another land's lock commit (`held` or `free`), taken ten minutes ago, pushed onto the lock branch's tip."""
    when = f"@{int(datetime.now(UTC).timestamp()) - 600} +0000"
    tip = git_in(lands["origin"], "for-each-ref", "--format=%(objectname)", REF).strip()
    tree = git_in(lands["work"], "hash-object", "-t", "tree", "-w", os.devnull).strip()
    commit = subprocess.run(
        [
            "git",
            "commit-tree",
            *(["-p", tip] if tip else []),
            "-m",
            f"{title} [skip ci]\n\npid 1, nonce {len(tip)}{title[-4:] == "free"}",
            tree,
        ],
        cwd=lands["work"],
        env={**os.environ, "GIT_COMMITTER_DATE": when},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git_in(lands["work"], "push", "-q", "origin", f"{commit}:{REF}")


@pytest.fixture
def one_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--wait` ends after its first try, so a test reads what a land did before its first wait."""
    monkeypatch.setattr(approvals, "POLL", approvals.CEILING + 1)


def draft(lands: dict[str, Any], number: int, **fields: Any) -> None:
    lands["open"](number, {f"{number}.txt": f"{number}\n"}, **fields)
    lands["pulls"][number]["isDraft"] = True


def readied(lands: dict[str, Any]) -> list[str]:
    return [call[-1] for call in lands["calls"] if call[:2] == ("pr", "ready")]


def test_a_draft_is_readied_before_the_first_wait_for_the_lock(
    lands: dict[str, Any], one_wait: None
) -> None:
    draft(lands, 7)
    lock(lands, approvals.HELD)
    assert lands["land"]("7", "--wait")[0] == approvals.WAITING
    assert (readied(lands), lands["pulls"][7]["isDraft"], lands["merged"]()) == (["7"], False, [])


def test_a_draft_missing_its_proof_is_not_readied_while_it_waits_and_keeps_its_message(
    lands: dict[str, Any], one_wait: None
) -> None:
    draft(lands, 7, reviews=())
    lock(lands, approvals.HELD)
    assert lands["land"]("7", "--wait")[0] == approvals.WAITING
    assert readied(lands) == []
    lock(lands, approvals.FREE)
    code, lines = lands["land"]("7")
    assert (code, readied(lands), lands["merged"]()) == (1, [], [])
    assert lines and all("is ready now" not in line for line in lines), lines


def test_a_batch_started_while_a_draft_waits_lists_it_among_its_candidates(
    lands: dict[str, Any], one_wait: None
) -> None:
    draft(lands, 7)
    lock(lands, approvals.HELD)
    lands["land"]("7", "--wait")
    lock(lands, approvals.FREE)
    # the holder's next batch is a bare land: it never names #7
    assert lands["land"]()[0] == 0
    assert lands["merged"]() == ["7"]


def test_several_named_drafts_are_readied_and_land_in_one_batch(lands: dict[str, Any]) -> None:
    draft(lands, 7)
    draft(lands, 8)
    assert lands["land"]("7", "8")[0] == 0
    assert (readied(lands), lands["merged"](), lands["runs"]()) == (["7", "8"], ["7", "8"], 1)


def test_a_named_pr_missing_its_proof_is_left_out_with_its_reason_and_the_rest_land(
    lands: dict[str, Any],
) -> None:
    draft(lands, 7)
    draft(lands, 8, reviews=())
    code, lines = lands["land"]("7", "8")
    assert (code, readied(lands), lands["merged"]()) == (1, ["7"], ["7"])
    assert any(line.startswith("PR #8") for line in lines), lines


def test_only_limits_the_batch_to_the_named_prs(lands: dict[str, Any]) -> None:
    lands["open"](5, {"5.txt": "5\n"})
    draft(lands, 7)
    draft(lands, 8)
    assert lands["land"]("7", "8", "--only")[0] == 0
    assert lands["merged"]() == ["7", "8"]


def test_the_exit_is_the_worst_of_the_named_prs_one_over_three_over_zero(
    lands: dict[str, Any], hub: dict[str, list[dict[str, Any]]]
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    lands["open"](8, {".github/ci.yml": "on: push\n"})
    lands["pulls"][8]["files"] = {"nodes": [{"path": ".github/ci.yml"}]}
    assert lands["land"]("7", "8")[0] == approvals.WAITING  # #8 waits for the owner, #7 lands
    assert lands["merged"]() == ["7"]
    lands["open"](9, {"9.txt": "9\n"}, reviews=())
    assert lands["land"]("8", "9")[0] == 1


def test_a_named_pr_of_another_base_or_closed_is_left_out_and_exits_one(
    lands: dict[str, Any],
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    lands["open"](8, {"8.txt": "8\n"})
    lands["pulls"][8]["state"] = "CLOSED"
    code, lines = lands["land"]("7", "8")
    assert (code, lands["merged"]()) == (1, ["7"])
    assert "PR #8 is closed: nothing to land" in lines


def test_a_cloud_session_leaves_a_named_draft_for_landable_to_refuse(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "in_cloud", lambda: True)
    draft(lands, 7)
    assert lands["land"]("7")[0] == 1
    assert readied(lands) == []
