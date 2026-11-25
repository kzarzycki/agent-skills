"""`queue_duty` names the one team that holds queue duty (#2500): it raises the merge queue's failures that are not one
PR's fault. A policy without the section leaves every team holding it, so a project with one team changes nothing."""

from __future__ import annotations

import pytest
from approvals_harness import approvals


def policy(*lines: str) -> object:
    return approvals.Policy("# G\n\n## Policy\n\n```yaml\n" + "\n".join(lines) + "\n```\n")


def test_no_section_means_every_team_holds_the_duty(monkeypatch) -> None:
    monkeypatch.setattr(approvals, "viewer", lambda: "ci")
    assert approvals.queue_duty_held(policy("team: {}"))
    assert approvals.queue_duty_held(None)


def test_only_the_named_team_holds_it(monkeypatch) -> None:
    monkeypatch.setattr(approvals, "viewer", lambda: "ci")
    assert approvals.queue_duty_held(policy("team:", "  name: a", "queue_duty:", "  team: a"))
    assert not approvals.queue_duty_held(policy("team:", "  name: b", "queue_duty:", "  team: a"))


def test_a_team_without_a_name_holds_none(monkeypatch) -> None:
    monkeypatch.setattr(approvals, "viewer", lambda: None)
    assert not approvals.queue_duty_held(policy("queue_duty:", "  team: a"))


def test_the_account_is_the_team_where_the_policy_names_none(monkeypatch) -> None:
    monkeypatch.setattr(approvals, "viewer", lambda: "a")
    assert approvals.queue_duty_held(policy("queue_duty:", "  team: a"))


def test_a_section_without_its_team_is_refused() -> None:
    with pytest.raises(approvals.Refused):
        approvals.queue_duty_held(policy("queue_duty: {}"))
