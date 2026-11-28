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


def test_a_copy_whose_source_is_unchanged_keeps_its_source(tmp_path, monkeypatch) -> None:
    git = _repo(tmp_path)
    (tmp_path / "mise.toml").write_text("[tasks]\nx = 1\ny = 2\nz = 3\n")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").strip()
    (tmp_path / "copied.md").write_text("[tasks]\nx = 1\ny = 2\nz = 3\n")
    git("add", "-A")
    git("commit", "-qm", "copy")
    head = git("rev-parse", "HEAD").strip()
    monkeypatch.chdir(tmp_path)
    paths = os_.changed_paths(head, None, base)
    patch = os_.range_diff(head, None, base)
    assert "copy from mise.toml" in patch and "copy to copied.md" in patch
    assert paths == ["mise.toml", "copied.md"]
    assert os_.tier(paths, ["*.md"], INPUTS)["review"] is True


def test_a_path_with_spaces_reaches_nearby_code_and_the_gate_config_finding(
    tmp_path, monkeypatch
) -> None:
    git = _repo(tmp_path)
    (tmp_path / "keep").write_text("k")
    git("add", "-A")
    git("commit", "-qm", "base")
    (tmp_path / "dir").mkdir()
    (tmp_path / "dir/test config.py").write_text("".join(f"line {n}\n" for n in range(1, 30)))
    git("add", "-A")
    git("commit", "-qm", "change")
    first = git("rev-parse", "HEAD").strip()
    (tmp_path / "dir/test config.py").write_text(
        "changed\n" + "".join(f"line {n}\n" for n in range(2, 30))
    )
    git("add", "-A")
    git("commit", "-qm", "edit")
    head = git("rev-parse", "HEAD").strip()
    (tmp_path / "spec.md").write_text("the spec")
    (tmp_path / "rules.md").write_text("RULE_TEXT: no mocks")
    policy = POLICY.replace("    - uv.lock\n", '    - uv.lock\n    - "dir/test config.py"\n', 1)
    (tmp_path / "policy.md").write_text(policy)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os_, "trusted_gate", lambda h: GATE[:2])
    monkeypatch.setattr(os_, "run_gate", lambda h: GATE[2])
    out: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: out.append(" ".join(map(str, a))))
    argv = ["bundle", "--head", head, "--spec", "spec.md", "--policy", "policy.md"]
    assert os_.main([*argv, "--against", first, "--rules", "rules.md", "--nearby-from-git"]) == 0
    text = out[0]
    nearby = text.split("## Nearby code")[1].split("## Diff")[0]
    assert "line 29" in nearby and "line 29" not in text.split("## Diff")[1]  # outside the hunk
    assert "RULE_TEXT: no mocks" in text.split("## Rules")[1].split("## Nearby code")[0]
    assert "FINDING (gate config): dir/test config.py" in text
    assert "RAW_GATE_OUTPUT: lint ok" in text


REVIEW = {
    "criteria": ["Same head refused: ran the planner"],
    "findings": [
        {
            "priority": "P1",
            "title": "t",
            "location": "a.py:1",
            "body": "b",
            "rules": ["R"],
            "breaks": "Acceptance line 1",
        }
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


UNRUN = {"check": "Pilot", "command": "mise run pilot -- --heads 10"}
MUTATION = {
    "check": "mutation: drop the guard",
    "command": "uv run pytest -n 0 loop/tests/test_one_shot.py -k guard",
    "mutation": {
        "patch": "s/> MAX_CALLS/> 99/ in one_shot.py",
        "undo": "git checkout -- one_shot.py",
        "redo": "sed -i s/MAX/99/ one_shot.py",
    },
}


def test_an_unrun_check_goes_to_the_proof_run_with_what_the_lead_needs(tmp_path) -> None:
    review = {**REVIEW, "findings": [], "overall_correctness": "patch is correct"}
    report, question = os_.verdict(
        {**review, "acceptance_not_run": [UNRUN, MUTATION]}, H, "codex", 1
    )
    assert report is None and "owner action" not in question
    for needed in (
        UNRUN["command"],
        MUTATION["command"],
        "s/> MAX_CALLS/> 99/",
        "git checkout -- one_shot.py",
        "sed -i s/MAX/99/",
    ):
        assert needed in question
    for bad in ("Pilot", {"check": "x"}, {**MUTATION, "mutation": {"patch": "p"}}):
        with pytest.raises(os_.Refused):
            os_.verdict({**review, "acceptance_not_run": [bad]}, H, "codex", 1)
    # a step only the owner can take is the gatekeeper's own `Not run: ..., owner action:` line
    owner = {**review, "owner_only_not_run": ["sign the release"], "owner_action": "sign it"}
    got = facts(tmp_path, owner)
    assert got["satisfied"] is False and got["verdict"] == {"blocker": 0, "major": 0, "minor": 0}


def test_the_cli_writes_a_question_file_and_exits_3_for_an_unrun_check(tmp_path) -> None:
    review = tmp_path / "r.json"
    review.write_text(
        json.dumps({**REVIEW, "findings": [], "acceptance_not_run": [UNRUN, MUTATION]})
    )
    out = tmp_path / "rep.md"
    argv = ["verdict", "--json", str(review), "--head", H, "--family", "codex", "--pass", "1"]
    assert os_.main([*argv, "--report", str(out)]) == 3
    question = (tmp_path / "rep.md.question").read_text()
    assert (
        not out.exists()
        and "undo: git checkout -- one_shot.py" in question
        and UNRUN["command"] in question
    )


def test_the_briefs_example_is_accepted_by_the_verdict_cli_and_blank_fields_are_not(
    tmp_path,
) -> None:
    brief = (ROOT / "loop/skills/engineering-loop/one-shot-verifier.md").read_text()
    example = json.loads(brief.split("```json\n")[1].split("```")[0])
    review = tmp_path / "r.json"
    review.write_text(json.dumps(example))
    argv = ["verdict", "--json", str(review), "--head", H, "--family", "codex", "--pass", "1"]
    assert os_.main([*argv, "--report", str(tmp_path / "a.md")]) == 3
    for field in ("check", "command", "patch", "undo", "redo"):
        item = json.loads(json.dumps(MUTATION))
        (item["mutation"] if field in item["mutation"] else item)[field] = "  "
        review.write_text(json.dumps({**example, "acceptance_not_run": [item]}))
        report = tmp_path / f"{field}.md"
        assert os_.main([*argv, "--report", str(report)]) == 2, field
        assert not Path(f"{report}.question").exists(), field


STEP_PY = """import fcntl, os, pathlib, subprocess, sys

name = sys.argv[1]
held = os.environ.get("LOOP_GATE_SLOT_HELD", "")
if held:
    # a second open file description: the parent's exclusive lock on the slot refuses this one while it is held
    probe = os.open(held, os.O_WRONLY)
    try:
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        slot = "free"
    except BlockingIOError:
        slot = "locked"
else:
    slot = "none"
print(f"CHILD:{name} mode={os.environ.get('PROBE_GATE_MODE', 'missing')} base={os.environ.get('GATE_BASE', 'filtered')} slot={slot}")
pathlib.Path("MARKERS/ran-" + name).write_text("ran")
action = os.environ.get("PROBE_" + name.upper(), "")
if action == "rewrite":
    pathlib.Path("tracked.txt").write_text("changed by the gate")
if action == "restore":
    pathlib.Path("tracked.txt").write_text("original")
if action == "commit":
    subprocess.run(["git", "commit", "--allow-empty", "-qm", "gate"], check=True)
if action == "fail":
    sys.exit(3)
"""
POLICY_STEPS = """## Policy

```yaml
loop:
  gate_steps:
    - name: first
      command: PROBE_GATE_MODE=strict python3 step.py first
      where: any
    - name: second
      command: PROBE_GATE_MODE=strict python3 step.py second
      where: any
```
"""


def _gate_checkout(tmp_path, monkeypatch):
    """A clean scratch repo whose policy gate has two steps (`first`, `second`) running step.py, and a bundle argv for
    it. Each step writes its own marker file in `markers` (outside the repo), so a run of either is observable."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git = _repo(repo)
    (repo / "docs/agents").mkdir(parents=True)
    (repo / "docs/agents/gatekeeper.md").write_text(POLICY_STEPS)
    markers = tmp_path / "markers"
    markers.mkdir()
    (repo / "step.py").write_text(STEP_PY.replace('"MARKERS/ran-"', f"{str(markers) + '/ran-'!r}"))
    (repo / "tracked.txt").write_text("original")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD").strip()
    (repo / "extra.txt").write_text("e")
    git("add", "-A")
    git("commit", "-qm", "head")
    head = git("rev-parse", "HEAD").strip()
    (tmp_path / "spec.md").write_text("spec")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("GATE_BASE", "ambient-leak")
    # an isolated slot directory with locking on, whatever this host's own settings are
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("GATE_SLOTS", "2")
    monkeypatch.delenv("LOOP_GATE_SLOT_HELD", raising=False)
    monkeypatch.setattr(os_, "trusted_gate", lambda h: (0, "recorded"))
    argv = ["bundle", "--head", head, "--spec", str(tmp_path / "spec.md")]
    argv += ["--policy", "docs/agents/gatekeeper.md", "--against", base]
    return repo, git, markers, argv


def _ran(markers):
    return sorted(p.name for p in markers.iterdir())


def test_the_bundle_cli_runs_each_step_in_the_gatekeepers_env_holding_a_locked_slot(
    tmp_path, monkeypatch, capsys
) -> None:
    _, _, markers, argv = _gate_checkout(tmp_path, monkeypatch)
    assert os_.main(argv) == 0
    text = capsys.readouterr().out
    # the child's own lines: the step's variable set, the ambient gate base filtered out, and the slot's lock refusing
    # a second open of it (a slot named but not locked reads `free`)
    for name in ("first", "second"):
        assert f"\nCHILD:{name} mode=strict base=filtered slot=locked\n" in text
    assert "[exit 0]" in text and _ran(markers) == ["ran-first", "ran-second"]


def test_a_failing_gate_step_prints_no_bundle_and_the_next_step_never_runs(
    tmp_path, monkeypatch, capsys
) -> None:
    _, _, markers, argv = _gate_checkout(tmp_path, monkeypatch)
    monkeypatch.setenv("PROBE_FIRST", "fail")
    assert os_.main(argv) == 2
    seen = capsys.readouterr()
    assert seen.out == "" and "fails" in seen.err and _ran(markers) == ["ran-first"]


def test_the_checkout_is_verified_before_every_step_runs(tmp_path, monkeypatch, capsys) -> None:
    _, git, markers, argv = _gate_checkout(tmp_path, monkeypatch)
    # the first step rewrites a tracked file and the second would restore it: only a check between them sees it
    monkeypatch.setenv("PROBE_FIRST", "rewrite")
    monkeypatch.setenv("PROBE_SECOND", "restore")
    assert os_.main(argv) == 2
    assert "changed the checkout" in capsys.readouterr().err and _ran(markers) == ["ran-first"]
    git("checkout", "--", "tracked.txt")
    (markers / "ran-first").unlink()
    # the first step makes a clean commit: HEAD moved though nothing is dirty
    monkeypatch.setenv("PROBE_FIRST", "commit")
    monkeypatch.delenv("PROBE_SECOND")
    assert os_.main(argv) == 2
    assert "changed the checkout" in capsys.readouterr().err and _ran(markers) == ["ran-first"]


@pytest.mark.parametrize("action", ["rewrite", "commit"])
def test_the_checkout_is_verified_after_the_final_step_too(
    tmp_path, monkeypatch, capsys, action
) -> None:
    _, _, markers, argv = _gate_checkout(tmp_path, monkeypatch)
    monkeypatch.setenv("PROBE_SECOND", action)
    assert os_.main(argv) == 2
    seen = capsys.readouterr()
    assert seen.out == "" and "changed the checkout" in seen.err
    assert _ran(markers) == ["ran-first", "ran-second"]


def test_a_dirty_start_or_another_head_runs_no_step(tmp_path, monkeypatch, capsys) -> None:
    repo, git, markers, argv = _gate_checkout(tmp_path, monkeypatch)
    # a hidden untracked file is still a dirty checkout
    git("config", "status.showUntrackedFiles", "no")
    (repo / "local.cfg").write_text("x")
    assert os_.main(argv) == 2
    assert "uncommitted" in capsys.readouterr().err and _ran(markers) == []
    (repo / "local.cfg").unlink()
    # the checkout is at the PR's head, not the one asked for
    other = git("rev-parse", "HEAD~1").strip()
    argv[argv.index("--head") + 1] = other
    assert os_.main(argv) == 2
    assert "not at" in capsys.readouterr().err and _ran(markers) == []


def test_a_missing_record_through_the_bundle_cli_runs_no_step(
    tmp_path, monkeypatch, capsys
) -> None:
    _, _, markers, argv = _gate_checkout(tmp_path, monkeypatch)
    monkeypatch.setattr(os_, "trusted_gate", lambda h: (1, "no record"))
    assert os_.main(argv) == 2
    seen = capsys.readouterr()
    assert "no gate record" in seen.err and seen.out == "" and _ran(markers) == []


def test_a_p1_finding_carries_its_breaks_path_and_origin_lines_to_the_report(tmp_path) -> None:
    finding = {
        **REVIEW["findings"][0],
        "breaks": "standing bar security",
        "path": "a forged token",
        "origin": "new",
    }
    got = facts(tmp_path, {**REVIEW, "findings": [finding]})
    body = got["findings"][0]["body"]
    assert (
        "Breaks: standing bar security" in body
        and "Path: a forged token" in body
        and "Origin: new" in body
    )


def test_a_p1_finding_with_no_breaks_is_refused_by_the_report_parser(tmp_path) -> None:
    finding = {k: v for k, v in REVIEW["findings"][0].items() if k != "breaks"}
    with pytest.raises(gatekeeper.Refused, match="no .Breaks:"):
        facts(tmp_path, {**REVIEW, "findings": [finding]})
