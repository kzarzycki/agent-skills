"""approvals.py: a PR whose test selection is the whole suite is queued in a batch of its own (#2553).

`land` labels such a PR `loop:solo` before `loop:queued`; the rendered `.mergify.yml` has a `solo` queue rule
(`batch_size: 1`) that takes it, and the `default` rule one without the label. The trigger is the project's own
selection (`Gate: full`, no `Affected tests:` selector, a build input under `select.build_inputs_in_queue: full`),
never a path or a name the pack knows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from approvals_harness import (
    LOOP,
    add,
    approvals,
    lands,  # noqa: F401
)
from test_approvals_github_queue import labels_of, queue  # noqa: F401
from test_approvals_mergify_queue import land_statuses, mergify  # noqa: F401
from test_approvals_timeouts import TEMPLATE, checkout, policy_md, verb  # noqa: F401


def loop_with(state: dict[str, Any], *lines: str) -> None:
    loop = state["work"] / "docs" / "agents" / "loop.md"
    loop.write_text(loop.read_text() + "\n" + "\n".join(lines) + "\n")


def test_a_pr_with_no_selector_is_handed_over_alone(mergify: dict[str, Any]) -> None:
    head = mergify["opened"](7)
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    assert lines[-1] == f"PR #7 queued for Mergify at {head}"
    assert any("the whole suite" in line and "a batch of its own" in line for line in lines)
    assert {"loop:solo", "loop:queued"} <= labels_of(mergify, 7)


def test_a_gate_full_project_is_handed_over_alone(mergify: dict[str, Any]) -> None:
    loop_with(mergify, "Affected tests: ./select.sh", "Gate: full")
    mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    assert "loop:solo" in labels_of(mergify, 7)


def test_an_affected_tests_pr_is_handed_over_as_before(mergify: dict[str, Any]) -> None:
    loop_with(mergify, "Affected tests: ./select.sh")
    mergify["opened"](7, {"scripts/tool.py": "print('changed')\n"})
    code, lines = mergify["land"]("7")
    assert code == 0, lines
    labels = labels_of(mergify, 7)
    assert "loop:queued" in labels and "loop:solo" not in labels


def test_a_stale_solo_label_comes_off_when_the_selection_narrows(mergify: dict[str, Any]) -> None:
    mergify["opened"](7)
    assert mergify["land"]("7")[0] == 0
    assert "loop:solo" in labels_of(mergify, 7)
    # the selection is now affected tests, and the PR is handed over again at a new head
    loop_with(mergify, "Affected tests: ./select.sh")
    pull = {"headRefOid": "x", "baseRefName": "main"}
    assert approvals.whole_suite(pull) is None


def test_a_build_input_is_the_whole_suite_only_under_full(
    mergify: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_with(mergify, "Affected tests: ./select.sh")
    pull = {"headRefOid": "h", "baseRefName": "main"}
    monkeypatch.setattr(approvals, "merge_base_of", lambda base, head: "b")
    monkeypatch.setattr(approvals, "selected", lambda base, head=None: (["build.cfg"], []))
    for value, expected in (("full", True), ("floor", False)):
        monkeypatch.setattr(
            approvals,
            "settings",
            lambda _p, value=value: {
                "select": {"build_inputs": ["build.cfg"], "build_inputs_in_queue": value}
            },
        )
        got = approvals.whole_suite(pull)
        assert (got is not None) == expected, (value, got)
        assert not expected or "build.cfg" in got


def test_the_rendered_config_has_a_solo_rule_beside_the_default() -> None:
    config = yaml.safe_load(approvals.mergify_rendered(None))
    rules = {rule["name"]: rule for rule in config["queue_rules"]}
    assert list(rules) == ["default", "solo"]
    assert rules["solo"]["batch_size"] == 1 and rules["default"]["batch_size"] == 3
    assert "label = loop:solo" in rules["solo"]["queue_conditions"]
    assert "-label = loop:solo" in rules["default"]["queue_conditions"]
    routed = {
        rule["actions"]["queue"]["name"]: rule["conditions"]
        for rule in config["pull_request_rules"]
    }
    assert "label = loop:solo" in routed["solo"] and "-label = loop:solo" in routed["default"]


def test_the_policy_sets_the_default_batch_and_every_rules_timeout() -> None:
    policy = add(add(LOOP, "land", "batch_size: 5\n"), "timeouts", "run: 4h\n")
    config = yaml.safe_load(approvals.mergify_rendered(policy))
    rules = {rule["name"]: rule for rule in config["queue_rules"]}
    assert rules["default"]["batch_size"] == 5 and rules["solo"]["batch_size"] == 1
    assert rules["default"]["checks_timeout"] == rules["solo"]["checks_timeout"] == "4 hours"


def test_the_check_fails_when_the_solo_rule_drifts(checkout: Path) -> None:
    assert verb("--check")[0] == 0
    held = TEMPLATE.read_text()
    (checkout / ".mergify.yml").write_text(
        held.replace("    batch_size: 1\n", "    batch_size: 2\n")
    )
    code, out = verb("--check")
    assert code == 1 and "beyond `checks_timeout`" in out
    (checkout / ".mergify.yml").write_text(held.replace("label = loop:solo", "label = loop:alone"))
    assert verb("--check")[0] == 1
