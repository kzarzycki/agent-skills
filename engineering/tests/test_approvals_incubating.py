"""approvals.py: an `incubating` PR stops owing the requirements `incubating.waive` names, while it stays eligible."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    approvals,
    approved,
    issue,
    loop_md,
    pull,
    verdict_on,
)

BODY = "Incubates: #9\n"
POLICY = loop_md("incubating:\n  append_paths: [mise.toml]\n")


@pytest.fixture(autouse=True)
def epic(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The tracking epic #9, open and labelled `incubating`; a test edits it."""
    node = {**issue(9, "incubating", "epic"), "state": "OPEN"}
    monkeypatch.setattr(approvals, "issue_node", lambda _n: node)
    return node


def merge(
    files: list[dict[str, Any]], loop: str = POLICY, body: str = BODY, **fields: Any
) -> list[str]:
    pr = pull(body=body, labels=("incubating",), **fields)
    pr["files"] = {"nodes": files}
    issues = [approved(1, "area:web", "kind:enhancement")]
    return approvals.proofs("merge", pr, issues, loop)


def added(path: str) -> dict[str, Any]:
    return {"path": path, "changeType": "ADDED", "additions": 5, "deletions": 0}


def edited(path: str, deletions: int = 0) -> dict[str, Any]:
    return {"path": path, "changeType": "MODIFIED", "additions": 2, "deletions": deletions}


def test_added_files_owe_no_evidence_or_verifier() -> None:
    assert merge([added("new/skill.md")]) == []


def test_an_append_to_an_allowed_file_is_eligible() -> None:
    assert merge([added("new.py"), edited("mise.toml")]) == []


@pytest.mark.parametrize(
    "files, named",
    [
        ([edited("mise.toml", deletions=1)], "mise.toml"),
        ([edited("src/app.py")], "src/app.py"),
        ([{"path": "a.py", "changeType": "DELETED", "deletions": 3}], "a.py"),
        ([{"path": "b.py", "changeType": "RENAMED", "deletions": 0}], "b.py"),
        ([{"path": "mise.toml", "changeType": "MODIFIED"}], "mise.toml"),  # no count read: not zero
    ],
)
def test_touching_existing_code_owes_the_full_loop(files: list[dict[str, Any]], named: str) -> None:
    found = merge(files)
    assert any(named in line and "owes the full loop" in line for line in found)
    assert any("## Evidence" in line for line in found)  # the body has none, and none is waived
    assert any("verifier" in line.lower() or "review" in line.lower() for line in found)


def test_no_epic_line_owes_the_full_loop() -> None:
    found = merge([added("x.md")], body="")
    assert any("no `Incubates: #<epic>` line" in line for line in found)
    assert any("## Evidence" in line for line in found)


def test_a_closed_epic_owes_the_full_loop(epic: dict[str, Any]) -> None:
    epic["state"] = "CLOSED"
    assert any("not an open issue labelled `incubating`" in line for line in merge([added("x.md")]))


def test_a_high_risk_change_is_not_eligible() -> None:
    loop = loop_md("incubating:\n  append_paths: []\nrisk:\n  paths: [secure/**]\n")
    found = merge([added("secure/key.py")], loop=loop)
    assert any("rates high or critical" in line for line in found)


def test_waive_names_the_requirements_and_the_rest_stay_required() -> None:
    loop = loop_md("incubating:\n  waive: [evidence]\n")
    found = merge([added("x.md")], loop=loop)
    assert not any("## Evidence" in line for line in found)
    assert any("review" in line.lower() or "verifier" in line.lower() for line in found)


def test_an_unknown_waive_name_is_refused() -> None:
    with pytest.raises(approvals.Refused, match="coverage"):
        merge([added("x.md")], loop=loop_md("incubating:\n  waive: [speed]\n"))


def test_the_label_means_nothing_without_the_policy() -> None:
    found = merge([added("x.md")], loop=loop_md(), body="")
    assert any("## Evidence" in line for line in found)


def test_a_waived_verifier_still_reads_an_unresolved_thread() -> None:
    found = merge([added("x.md")], threads=(False,))
    assert any("unresolved" in line for line in found)


def test_a_verdict_that_exists_is_not_required_to_be_satisfied_but_threads_still_count() -> None:
    assert merge([added("x.md")], reviews=(verdict_on(HEAD),)) == []
