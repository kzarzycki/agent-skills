"""approvals.py: an incubating PR that adds a file on a risk path is not eligible, under `spec.auto` too (#1288)."""

from __future__ import annotations

import pytest
from approvals_harness import approvals, approved, issue, loop_md, pull

BODY = "Incubates: #9\n"
POLICY = (
    "spec:\n  auto: true\nincubating:\n  append_paths: []\n"
    "risk:\n  paths: [.github/**]\n  critical_paths: [CODEOWNERS]\n"
)


@pytest.fixture(autouse=True)
def epic(monkeypatch: pytest.MonkeyPatch) -> None:
    node = {**issue(9, "incubating", "epic"), "state": "OPEN"}
    monkeypatch.setattr(approvals, "issue_node", lambda _n: node)


def merge(path: str, loop: str = POLICY) -> list[str]:
    pr = pull(body=BODY, labels=("incubating",))
    pr["files"] = {"nodes": [{"path": path, "changeType": "ADDED", "additions": 5, "deletions": 0}]}
    return approvals.proofs(
        "merge", pr, [approved(1, "area:web", "kind:enhancement")], loop_md(loop)
    )


@pytest.mark.parametrize("path", [".github/workflows/x.yml", "CODEOWNERS"])
def test_an_added_file_on_a_risk_path_owes_the_full_loop(path: str) -> None:
    assert any("rates high or critical" in line for line in merge(path))


def test_an_added_file_elsewhere_stays_eligible() -> None:
    assert merge("new/skill.md") == []
