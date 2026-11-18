"""approvals.py: an eligible incubating PR's gate run takes `GATE_INCUBATING` and the waived names (#1288)."""

from __future__ import annotations

import os
from typing import Any

import pytest
from approvals_harness import approvals, loop_md, pull

BODY = "Incubates: #9\n"
NAMES = ["GATE_INCUBATING", "GATE_INCUBATING_WAIVES"]


@pytest.fixture(autouse=True)
def setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Epic #9 open and labelled; no env left over from or into another test."""
    node = {"number": 9, "state": "OPEN", "labels": {"nodes": [{"name": "incubating"}]}}
    monkeypatch.setattr(approvals, "issue_node", lambda _n: node)
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def made(body: str = BODY, path: str = "new.py") -> dict[str, Any]:
    pr = pull(body=body, labels=("incubating",))
    pr["files"] = {"nodes": [{"path": path, "changeType": "ADDED", "additions": 1, "deletions": 0}]}
    return pr


def test_an_eligible_pr_exports_the_flag_and_the_waived_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = loop_md("incubating:\n  waive: [full_gate, coverage]\n")
    assert approvals.tier(made(), policy) == NAMES
    assert os.environ["GATE_INCUBATING"] == "1"
    assert os.environ["GATE_INCUBATING_WAIVES"] == "coverage,full_gate"
    monkeypatch.delenv("GATE_INCUBATING")
    monkeypatch.delenv("GATE_INCUBATING_WAIVES")


def test_an_ineligible_pr_exports_nothing() -> None:
    policy = loop_md("incubating:\n  waive: [full_gate]\n")
    assert approvals.tier(made(body="no epic line"), policy) == []
    assert "GATE_INCUBATING" not in os.environ
