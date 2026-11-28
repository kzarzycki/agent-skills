"""scripts/one_shot.py: the one-shot verifier's deterministic steps (#2996)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "one_shot", ROOT / "loop/skills/engineering-loop/scripts/one_shot.py"
)
os_ = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(os_)

sys.path.insert(0, str(ROOT / "gatekeeper/skills/gatekeeper/scripts"))
import gatekeeper

H = "a" * 40
TREE = "b" * 40
POLICY = "loop:\n  gate: mise run check-fast\nselect:\n  build_inputs:\n    - pyproject.toml\n    - tools/affected_tests.py\n"
REC = json.dumps({"head": H, "tree": TREE, "command": "mise run check-fast", "exit": 0})
DIFF = "diff --git a/x.py b/x.py\n+1\n"


def build(diff=DIFF, rec=REC, **kw):
    return os_.bundle(H, "spec", diff, rec, "log text", TREE, POLICY, **kw)


def test_low_risk_paths_get_gates_only_with_a_reason() -> None:
    got = os_.tier(["docs/a.md", "docs/b.md"], ["docs/*"])
    assert got["review"] is False and "gates only" in got["reason"]
    assert os_.tier(["docs/a.md", "x.py"], ["docs/*"])["review"] is True


def test_gate_policy_edits_always_get_a_review_even_under_a_low_risk_glob() -> None:
    assert os_.tier(["docs/agents/gatekeeper.md"], ["docs/*"])["review"] is True
    assert os_.tier(["tools/affected_tests.py"], ["tools/*"])["review"] is True


def test_a_head_reviewed_twice_is_refused_and_a_later_pass_is_a_delta() -> None:
    with pytest.raises(os_.Refused):
        os_.plan("h2", [{"head": "h1"}, {"head": "h2"}])
    assert os_.plan("h1", []) == {"pass": 1, "base": None, "scope": "full"}
    assert os_.plan("h2", [{"head": "h1"}])["base"] == "h1"


def test_gate_config_edit_gets_a_finding_including_test_selection() -> None:
    for path in ("pyproject.toml", "tools/affected_tests.py", "docs/agents/gatekeeper.md"):
        diff = f"diff --git a/{path} b/{path}\n+x\n"
        assert f"FINDING (gate config): {path}" in build(diff)


def test_a_gate_result_not_from_the_gate_record_is_refused() -> None:
    bad_records = [
        "lead says tests passed",
        f"GATE head={H} exit=0 cmd=mise run check-fast",
        json.dumps({"head": "c" * 40, "tree": TREE, "command": "mise run check-fast", "exit": 0}),
        json.dumps({"head": H, "tree": "c" * 40, "command": "mise run check-fast", "exit": 0}),
        json.dumps({"head": H, "tree": TREE, "command": "true", "exit": 0}),
        json.dumps({"head": H, "tree": TREE, "command": "mise run check-fast", "exit": 1}),
    ]
    for bad in bad_records:
        with pytest.raises(os_.Refused):
            build(rec=bad)


def test_a_cut_or_a_missing_input_is_named_and_nearby_code_and_rules_are_included() -> None:
    assert "diff: cut at 50 of" in build(DIFF + "z" * 500, max_diff_bytes=50)
    out = build(nearby={"x.py": "def f(): pass"}, rules="R1: no mocks", max_part_bytes=8)
    assert "nearby x.py: cut at 8" in out and "rules: cut at 8" in out
    assert "### x.py" in out and "## Nearby code" in out and "## Rules" in out
    bare = build()
    assert "nearby code: not supplied" in bare and "rules: not supplied" in bare


REVIEW = {
    "criteria": ["Same head refused: ran the planner"],
    "findings": [
        {"priority": "P1", "title": "t", "location": "a.py:1", "body": "b", "rules": ["R"]}
    ],
    "overall_correctness": "patch is incorrect",
    "risk": "low — helpers only",
}


def report(tmp_path, review, **kw):
    path = tmp_path / "r.md"
    path.write_text(os_.verdict(review, H, "codex", 1, **kw))
    return path


def test_the_verdict_is_read_by_the_real_report_parser_and_keeps_the_guard_marker(tmp_path) -> None:
    facts = gatekeeper.report_facts(report(tmp_path, REVIEW, calls=31, credits=2.5))
    assert (
        facts["verdict"] == {"blocker": 0, "major": 1, "minor": 0} and facts["satisfied"] is False
    )
    assert "31 model calls over the 30 limit" in facts["verifier"]["qualifier"]
    assert "2.5 credits over the 2.0 limit" in facts["verifier"]["qualifier"]
    clean = {**REVIEW, "findings": [], "overall_correctness": "patch is correct"}
    facts = gatekeeper.report_facts(report(tmp_path, clean, calls=5, credits=1.0))
    assert facts["satisfied"] is True and facts["verifier"]["qualifier"] == ""
