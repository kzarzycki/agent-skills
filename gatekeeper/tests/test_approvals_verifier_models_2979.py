"""approvals.py: loop.md's `verifier:` section takes `models` (a model id per risk level) and `effort`, and the rating a
verifier start reads is the one `check merge` gives the PR (#2979)."""

from __future__ import annotations

import pytest
from approvals_harness import add, approvals, loop_md, pull


def test_the_verifier_section_takes_models_by_risk_level_and_an_effort() -> None:
    policy = add(loop_md(), "verifier", "models:\n  low: id-a\n  default: id-b\neffort: medium\n")
    assert approvals.settings(policy)["verifier"] == {
        "models": {"low": "id-a", "default": "id-b"},
        "effort": "medium",
    }


def test_a_level_models_does_not_know_is_refused_naming_the_nearest() -> None:
    policy = add(loop_md(), "verifier", "models:\n  highh: id-a\n")
    with pytest.raises(approvals.Refused, match="did you mean `high`"):
        approvals.settings(policy)


def test_a_model_id_must_be_a_string() -> None:
    policy = add(loop_md(), "verifier", "models:\n  low: 3\n")
    with pytest.raises(approvals.Refused, match="verifier.models.low"):
        approvals.settings(policy)


def test_the_level_a_verifier_start_reads_is_the_one_the_gate_rates() -> None:
    plain = loop_md()
    assert approvals.risk_level(pull(), [], plain) == "low"
    assert approvals.risk_level(pull(labels=("risk:high",)), [], plain) == "high"
    critical = add(plain, "risk", "critical_paths:\n  - src/orders/**\n")
    assert approvals.risk_level(pull(files=("src/orders/a.py",)), [], critical) == "critical"
    assert approvals.risk_level(pull(files=("README.md",)), [], critical) == "low"
