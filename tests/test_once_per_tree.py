"""R1, once per tree (#2140): a ready PR's CI reads the pass record of the head's tree, and the loop's text names one run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from tools import pr_head_record

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "loop" / "skills" / "engineering-loop"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "engineering-ci.yml"
SKIP = "steps.record.outputs.recorded != 'true'"


def test_pr_head_steps_skip_on_a_record_and_the_job_still_runs():
    job = yaml.safe_load(WORKFLOW.read_text())["jobs"]["qualify"]
    assert "if" not in job  # qualify is required: it runs and reports on every PR
    lookup = next(s for s in job["steps"] if s.get("id") == "record")
    assert (
        lookup["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    )  # the head, not the merge commit
    assert "pr_head_record.py" in lookup["run"]
    fast = next(s for s in job["steps"] if s.get("run") == "mise run check-fast")
    whitespace = next(s for s in job["steps"] if s.get("name") == "Check changed-file whitespace")
    assert SKIP in fast["if"]
    # the record proves check-fast only, which never runs `git diff --check`: whitespace runs either way
    assert "steps.record" not in whitespace["if"]


def test_the_record_ci_reads_is_the_command_ci_would_run():
    policy = (REPOSITORY / "docs" / "agents" / "gatekeeper.md").read_text()
    gate = next(line for line in policy.splitlines() if line.strip().startswith("gate:"))
    assert gate.split()[-3:] == ["mise", "run", "check-fast"]


def test_lookup_reports_a_record_and_treats_any_failure_as_none(monkeypatch):
    def fake(code: int, out: str):
        return lambda *a, **k: subprocess.CompletedProcess(a, code, out, "")

    monkeypatch.setattr(
        pr_head_record.subprocess, "run", fake(0, "recorded: tree T as loop-gate/T-k at now\n")
    )
    assert pr_head_record.lookup("abc")[0] is True
    monkeypatch.setattr(
        pr_head_record.subprocess, "run", fake(1, "no record of `x` on tree T: run it\n")
    )
    assert pr_head_record.lookup("abc")[0] is False
    monkeypatch.setattr(
        pr_head_record.subprocess, "run", fake(1, "recorded: one step passed, another has none\n")
    )
    assert (
        pr_head_record.lookup("abc")[0] is False
    )  # a failed exit is no record whatever it printed
    monkeypatch.setattr(
        pr_head_record.subprocess, "run", fake(0, "no tree for abc: run the tests\n")
    )
    assert pr_head_record.lookup("abc")[0] is False

    def boom(*a, **k):
        raise OSError("no uv")

    monkeypatch.setattr(pr_head_record.subprocess, "run", boom)
    assert pr_head_record.lookup("abc")[0] is False


def test_main_writes_the_step_outputs_and_exits_zero(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(
        pr_head_record, "lookup", lambda head: (True, "recorded: T as loop-gate/T-k")
    )
    assert pr_head_record.main(["abc"]) == 0
    assert out.read_text() == "recorded=true\nrecord=recorded: T as loop-gate/T-k\n"
    out.unlink()
    monkeypatch.setattr(pr_head_record, "lookup", lambda head: (False, "no record"))
    assert pr_head_record.main(["abc"]) == 0
    assert out.read_text() == "recorded=false\nrecord=no record\n"


def read(name: str) -> str:
    return " ".join((SKILL / name).read_text().split())


def test_loop_text_names_one_run_per_tree():
    skill, worker, verifier = read("SKILL.md"), read("worker.md"), read("verifier.md")
    assert "a push runs `test:changed` and `check:secrets`" not in skill
    assert "the worker's one affected-test run" in skill
    assert "says which record it found" in skill and "R1" in skill
    assert "the push hook's run is the run you report" in worker
    assert "run `approvals.py local-ci --record` once" in worker
    # the record CI reads must be one the loop lets the worker make: no older line forbids it
    assert (
        "no `local-ci`" not in worker
        and "The worker's own session makes one on its final head" in skill
    )
    assert "whose tree is the head's tree" in verifier and "run nothing again" in verifier
