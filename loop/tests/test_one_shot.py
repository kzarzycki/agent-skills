"""scripts/one_shot.py: the one-shot verifier's deterministic steps (#2996)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "one_shot", Path(__file__).parents[1] / "skills/engineering-loop/scripts/one_shot.py"
)
os_ = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(os_)

H = "abc123"
GATE = f"GATE head={H} exit=0 cmd=mise run check-fast\nall green\n"
DIFF = "diff --git a/x.py b/x.py\n+1\n"


def test_low_risk_paths_get_gates_only_with_a_reason() -> None:
    got = os_.tier(["docs/a.md", "docs/b.md"], ["docs/*"])
    assert got["review"] is False and "gates only" in got["reason"]
    assert os_.tier(["docs/a.md", "x.py"], ["docs/*"])["review"] is True


def test_a_head_reviewed_twice_is_refused_and_a_later_pass_is_a_delta() -> None:
    with pytest.raises(os_.Refused):
        os_.plan("h2", [{"head": "h1"}, {"head": "h2"}])
    assert os_.plan("h1", []) == {"pass": 1, "base": None, "scope": "full"}
    assert os_.plan("h2", [{"head": "h1"}])["base"] == "h1"


def test_gate_config_edit_gets_a_finding_and_self_reported_gates_are_refused() -> None:
    diff = "diff --git a/pyproject.toml b/pyproject.toml\n+x\n"
    assert "FINDING (gate config): pyproject.toml" in os_.bundle(H, "spec", diff, GATE)
    for bad in (
        "lead says tests passed\n",
        "GATE head=other exit=0 cmd=c\n",
        f"GATE head={H} exit=1 cmd=c\n",
    ):
        with pytest.raises(os_.Refused):
            os_.bundle(H, "spec", DIFF, bad)


def test_a_cut_is_named_in_the_bundle() -> None:
    out = os_.bundle(H, "spec", DIFF + "z" * 500, GATE, max_diff_bytes=50)
    assert "diff: cut at 50 of" in out
    assert "## Cuts\nnone" in os_.bundle(H, "spec", DIFF, GATE)


def test_verdict_maps_priorities_and_marks_a_runaway_pass() -> None:
    review = {
        "findings": [
            {"priority": "P1", "title": "t", "location": "a:1", "body": "b", "rules": ["R"]}
        ],
        "overall_correctness": "patch is incorrect",
    }
    text = os_.verdict(review, H, calls=31, credits=2.5)
    assert "VERDICT: 0 blocker, 1 major, 0 minor" in text and "SATISFIED: no" in text
    assert "Runaway guard: 31 model calls over the 30 limit; 2.5 credits over the 2.0 limit" in text
    clean = os_.verdict(
        {"overall_correctness": "patch is correct", "risk": "low — x"}, H, calls=5, credits=1.0
    )
    assert "SATISFIED: yes" in clean and "Runaway" not in clean
