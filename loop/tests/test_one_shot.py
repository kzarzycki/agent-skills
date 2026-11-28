"""scripts/one_shot.py: the one-shot verifier's deterministic steps (#2996)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "one_shot", ROOT / "loop/skills/engineering-loop/scripts/one_shot.py"
)
os_ = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(os_)
gatekeeper = os_.gatekeeper

H = "a" * 40
GATE = (0, "recorded: tree t, as refs/loop/records/x", "RAW_GATE_OUTPUT: lint ok, 12 passed")
INPUTS = ["pyproject.toml", "tools/affected_tests.py"]
DIFF = "diff --git a/x.py b/x.py\n+1\n"
POLICY = (ROOT / "docs/agents/gatekeeper.md").read_text()


def build(diff=DIFF, paths=("x.py",), gate=GATE, inputs=INPUTS, **kw):
    return os_.bundle(H, "spec", diff, list(paths), gate, inputs, **kw)


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


def test_a_build_input_only_in_the_policy_forces_review_and_a_finding_quoted_or_not() -> None:
    quoted = POLICY.replace("    - uv.lock\n", '    - uv.lock\n    - "ci/*.py"\n', 1)
    inputs = os_.build_inputs(quoted)
    assert "ci/*.py" in inputs and not any('"' in i for i in inputs)
    assert os_.tier(["ci/select.py"], ["ci/*"], inputs)["review"] is True
    diff = "diff --git a/ci/select.py b/ci/select.py\n+x\n"
    assert "FINDING (gate config): ci/select.py" in build(diff, ["ci/select.py"], inputs=inputs)


def test_gate_config_edit_gets_a_finding_including_test_selection() -> None:
    for path in ("pyproject.toml", "tools/affected_tests.py", "docs/agents/gatekeeper.md"):
        assert f"FINDING (gate config): {path}" in build(paths=[path])


def test_a_gate_result_the_gatekeeper_does_not_hold_is_refused(monkeypatch) -> None:
    with pytest.raises(os_.Refused):
        build(gate=(1, "no record of the gate on tree t: run it", "log"))
    with pytest.raises(os_.Refused):
        build(gate=(0, "recorded", "  "))
    # a caller's own JSON and log are not inputs at all
    with pytest.raises(SystemExit):
        os_.main(["bundle", "--head", H, "--spec", "s", "--policy", "p", "--gate-record", "r"])
    calls = []
    monkeypatch.setattr(
        os_.subprocess,
        "run",
        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 1, "no record", ""),
    )
    assert os_.trusted_gate(H) == (1, "no record")
    assert calls[0][-2:] == ["gate-record", H]


def test_a_cut_or_a_missing_input_is_named_and_nearby_code_and_rules_are_in_the_message() -> None:
    assert "diff: cut at 50 of" in build(DIFF + "z" * 500, max_diff_bytes=50)
    out = build(nearby={"x.py": "def f(): pass"}, rules="R1: no mocks", max_part_bytes=8)
    assert "nearby x.py: cut at 8" in out and "rules: cut at 8" in out
    bare = build()
    assert "nearby code: not supplied" in bare and "rules: not supplied" in bare


def _fetch(check_runs, log="RAW\nlint ok"):
    return lambda url: json.dumps({"check_runs": check_runs}) if "check-runs" in url else log


def test_the_raw_gate_log_is_the_forge_run_on_that_head_and_nothing_else_counts() -> None:
    run = {"id": 7, "name": "qualify", "head_sha": H, "conclusion": "success"}
    assert os_.ci_gate_log(H, repo="o/r", fetch=_fetch([run])) == "RAW\nlint ok"
    other = "c" * 40
    for bad in (
        [],
        [{**run, "head_sha": other}],
        [{**run, "conclusion": "failure"}],
        [{**run, "name": "lint"}],
    ):
        with pytest.raises(os_.Refused):
            os_.ci_gate_log(H, repo="o/r", fetch=_fetch(bad))
    with pytest.raises(os_.Refused):
        os_.ci_gate_log(H, repo="o/r", fetch=_fetch([run], log=" "))
    assert "RAW_GATE_OUTPUT: lint ok" in build()


def _repo(tmp_path):
    def git(*a):
        return subprocess.run(
            ["git", *a], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    return git


def test_a_rename_checks_both_sides_and_a_delta_uses_one_range(tmp_path, monkeypatch) -> None:
    git = _repo(tmp_path)
    (tmp_path / "mise.toml").write_text("[tasks]\nx = 1\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").strip()
    git("mv", "mise.toml", "README.md")
    git("commit", "-qm", "rename")
    first = git("rev-parse", "HEAD").strip()
    (tmp_path / "current.txt").write_text("c")
    git("add", "-A")
    git("commit", "-qm", "current")
    head = git("rev-parse", "HEAD").strip()
    monkeypatch.chdir(tmp_path)
    paths = os_.changed_paths(first, None, base)
    assert paths == ["mise.toml", "README.md"]
    assert os_.tier(paths, ["*.md"], INPUTS)["review"] is True
    # a delta since the last verdict is that range alone: the earlier rename is not in it
    assert os_.changed_paths(head, first) == ["current.txt"]
    assert "mise.toml" not in os_.range_diff(head, first, "origin/main")


def test_a_path_with_spaces_reaches_nearby_code_and_the_gate_config_finding(
    tmp_path, monkeypatch
) -> None:
    git = _repo(tmp_path)
    (tmp_path / "keep").write_text("k")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").strip()
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir/test config.py").write_text("NEARBY_SOURCE = 1\n")
    git("add", "-A")
    git("commit", "-qm", "change")
    head = git("rev-parse", "HEAD").strip()
    (tmp_path / "spec.md").write_text("the spec")
    (tmp_path / "rules.md").write_text("RULE_TEXT: no mocks")
    policy = POLICY.replace("    - uv.lock\n", '    - uv.lock\n    - "dir/test config.py"\n', 1)
    (tmp_path / "policy.md").write_text(policy)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os_, "trusted_gate", lambda h: GATE[:2])
    monkeypatch.setattr(os_, "ci_gate_log", lambda h, job: GATE[2])
    out: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: out.append(" ".join(map(str, a))))
    argv = ["bundle", "--head", head, "--spec", "spec.md", "--policy", "policy.md"]
    assert os_.main([*argv, "--against", base, "--rules", "rules.md", "--nearby-from-git"]) == 0
    text = out[0]
    assert "NEARBY_SOURCE = 1" in text and "RULE_TEXT: no mocks" in text
    assert "FINDING (gate config): dir/test config.py" in text
    assert "RAW_GATE_OUTPUT: lint ok" in text


REVIEW = {
    "criteria": ["Same head refused: ran the planner"],
    "findings": [
        {"priority": "P1", "title": "t", "location": "a.py:1", "body": "b", "rules": ["R"]}
    ],
    "overall_correctness": "patch is incorrect",
    "risk": "low — helpers only",
}


def facts(tmp_path, review, **kw):
    path = tmp_path / "r.md"
    report, question = os_.verdict(review, H, "codex", 1, **kw)
    assert question is None
    path.write_text(report)
    return gatekeeper.report_facts(path)


def test_the_brief_checklist_has_the_edge_input_line() -> None:
    brief = (ROOT / "loop/skills/engineering-loop/one-shot-verifier.md").read_text()
    assert "edge inputs" in brief and "parser or settings loader" in brief


def test_the_verdict_is_read_by_the_real_report_parser_and_keeps_the_guard_marker(tmp_path) -> None:
    got = facts(tmp_path, REVIEW, calls=31, credits=2.5)
    assert got["verdict"] == {"blocker": 0, "major": 1, "minor": 0} and got["satisfied"] is False
    assert "31 model calls over the 30 limit" in got["verifier"]["qualifier"]
    assert "2.5 credits over the 2.0 limit" in got["verifier"]["qualifier"]
    assert "### F1" not in got["criteria"] and "Same head refused" in got["criteria"]
    clean = {**REVIEW, "findings": [], "overall_correctness": "patch is correct"}
    got = facts(tmp_path, clean, calls=5, credits=1.0)
    assert got["satisfied"] is True and got["verifier"]["qualifier"] == ""


def test_an_unrun_check_goes_to_the_proof_run_question_never_an_owner_action(tmp_path) -> None:
    review = {**REVIEW, "findings": [], "overall_correctness": "patch is correct"}
    report, question = os_.verdict({**review, "acceptance_not_run": ["Pilot"]}, H, "codex", 1)
    assert report is None and "Pilot" in question and "owner action" not in question
    # a step only the owner can take is the gatekeeper's own `Not run: ..., owner action:` line
    owner = {**review, "owner_only_not_run": ["sign the release"], "owner_action": "sign it"}
    got = facts(tmp_path, owner)
    assert got["satisfied"] is False and got["verdict"] == {"blocker": 0, "major": 0, "minor": 0}


def test_the_cli_writes_a_question_file_and_exits_3_for_an_unrun_check(tmp_path) -> None:
    review = tmp_path / "r.json"
    review.write_text(json.dumps({**REVIEW, "findings": [], "acceptance_not_run": ["Pilot"]}))
    out = tmp_path / "rep.md"
    argv = ["verdict", "--json", str(review), "--head", H, "--family", "codex", "--pass", "1"]
    assert os_.main([*argv, "--report", str(out)]) == 3
    assert (tmp_path / "rep.md.question").exists() and not out.exists()
