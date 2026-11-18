"""approvals.py: a free landing lock goes to the land that began waiting first (#1216)."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

import pytest
from approvals_harness import (
    approvals,
    git_in,
    lands,  # noqa: F401
)


def waiter(lands: dict[str, Any], who: str, since: float, aged: int = 0) -> None:
    """Another land's waiting ref: began at `since`, last stamped `aged` seconds ago."""
    when = f"@{int(time.time()) - aged} +0000"
    tree = git_in(lands["work"], "hash-object", "-t", "tree", "-w", os.devnull).strip()
    commit = subprocess.run(
        ["git", "commit-tree", "-m", f"waiting [skip ci]\n\nsince {since:.0f}, PR #99, pid 1, nonce 0", tree],
        cwd=lands["work"],
        env={**os.environ, "GIT_COMMITTER_DATE": when},
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git_in(lands["work"], "push", "-q", "-f", "origin", f"{commit}:{approvals.WAITING.format('main', who)}")


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approvals, "waiting", True)
    monkeypatch.setattr(approvals, "waited", {"since": 0.0, "id": "", "base": ""})


def refs(lands: dict[str, Any]) -> list[str]:
    out = git_in(lands["origin"], "for-each-ref", "--format=%(refname)", "refs/heads/loop-waiting")
    return out.split()


def test_a_land_that_began_waiting_later_leaves_the_free_lock_to_the_older_waiter(
    lands: dict[str, Any], waits: None, capsys: pytest.CaptureFixture[str]
) -> None:
    waiter(lands, "aaaa", time.time() - 600)
    held: list[str] = []
    assert approvals.locked("main", held, 7) is False and held == []
    assert "PR #99 began waiting for the landing lock" in capsys.readouterr().out
    assert len(refs(lands)) == 2  # its own place is kept while it waits


def test_a_waiter_that_stopped_stamping_does_not_hold_up_the_next(lands: dict[str, Any], waits: None) -> None:
    waiter(lands, "aaaa", time.time() - 600, aged=approvals.WAITER_STALE + 60)
    assert approvals.locked("main", [], 7) is True


def test_a_younger_waiter_does_not_block_the_older(lands: dict[str, Any], waits: None) -> None:
    waiter(lands, "zzzz", time.time() + 600)
    assert approvals.locked("main", [], 7) is True


def test_taking_the_lock_deletes_the_lands_own_waiting_ref(lands: dict[str, Any], waits: None) -> None:
    assert approvals.locked("main", [], 7) is True
    assert refs(lands) == []


def test_a_land_without_wait_ignores_waiters_and_leaves_no_ref(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "waiting", False)
    waiter(lands, "aaaa", time.time() - 600)
    assert approvals.locked("main", [], 7) is True
    assert refs(lands) == [approvals.WAITING.format("main", "aaaa")]


def test_unwait_deletes_the_ref_and_forgets_the_place(lands: dict[str, Any], waits: None) -> None:
    approvals.stamp_wait("main", 7)
    assert len(refs(lands)) == 1
    approvals.unwait()
    assert refs(lands) == [] and approvals.waited["id"] == ""
