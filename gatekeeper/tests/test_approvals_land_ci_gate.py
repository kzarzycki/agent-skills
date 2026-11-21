"""`land`'s batch gate where the base requires a CI check (#1597): the check already ran each head's tests on that
exact head, so narrowed mode's selector does not run again over the batch; the batch gate is the `gate` line. Under
`ci: false`, or with no required check, the selector still gates the batch."""

from __future__ import annotations

from typing import Any

import pytest
from approvals_harness import approvals
from test_approvals_narrowed_gate import NO_CI, batch_of, repo  # noqa: F401  (repo is a fixture)


def test_with_a_required_check_the_batch_gate_runs_the_gate_line_not_the_selector(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    pulls = batch_of(repo, monkeypatch)
    loop = approvals.project()[1]  # as landing() reads it before the lock
    assert approvals.local_queue(pulls, "main", None, loop, {"qualify"}) == (0, False)
    ran = repo["ran"]()
    assert not [line for line in ran if line.startswith("selected")]
    assert ran == [
        "mise run check:all base=unset"
    ]  # the default `gate` line, with no base to select against
    [(landed, *_)] = repo["merged"]
    assert [pull["number"] for pull, *_ in landed] == [7, 8]


def test_under_ci_false_the_selector_gates_the_batch_even_with_a_required_check(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n\n" + NO_CI)
    pulls = batch_of(repo, monkeypatch)
    tip = repo["base"]()
    loop = approvals.project()[1]  # as landing() reads it before the lock
    assert approvals.local_queue(pulls, "main", None, loop, {"qualify"}) == (0, False)
    assert repo["ran"]() == [f"selected b.py c.py against {tip}"]


def test_batch_narrows_only_without_a_required_check_or_under_ci_false(
    repo: dict[str, Any],
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    assert approvals.batch_narrows(approvals.project()[1], set())
    assert not approvals.batch_narrows(approvals.project()[1], {"qualify"})
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n\n" + NO_CI)
    assert approvals.batch_narrows(approvals.project()[1], {"qualify"})
