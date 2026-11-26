"""The run before a PR is queued is the queue's selection in the queue's environment (#2455)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tools import affected_tests as a

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "loop" / "skills" / "engineering-loop"


def test_a_changed_skill_runs_the_repo_wide_rule_tests_it_did_not_change() -> None:
    """#2446: a skill's prose breaks the layer check without touching it; the selection holds it."""
    picked = set(a.targets(["loop/skills/engineering-loop/SKILL.md"]))
    assert {"tests/test_skill_layers.py", "tests/test_skill_references.py"} <= picked


def test_the_loop_runs_one_pre_queue_command_the_queue_selection_in_its_policy() -> None:
    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    assert tasks["check-affected"]["run"].splitlines()[-1] == "GATE_IN_QUEUE=1 CROSS_CHANGE_PR_HEAD=1 mise run test-batch"
    loop = (ROOT / "docs" / "agents" / "loop.md").read_text()
    assert re.search(r"^Affected tests:[ \t]*mise run check-affected[ \t]*$", loop, re.MULTILINE)


def test_the_selector_reads_the_queues_policy_from_that_command(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)  # no gatekeeper.md here: the queue policy is its default, `floor`
    assert a.queue_build_inputs() == "full"  # outside the queue, as the conftest leaves it
    monkeypatch.setenv("GATE_IN_QUEUE", "1")
    assert a.queue_build_inputs() == "floor"  # gatekeeper.md names no `build_inputs_in_queue`


def test_the_skill_names_the_pre_queue_run_for_the_lead_the_verifier_and_the_worker() -> None:
    for name in ("SKILL.md", "lead.md", "verifier.md"):
        assert "pre-queue run" in (LOOP / name).read_text(), name
    assert 'never "the changed test files"' in " ".join((LOOP / "SKILL.md").read_text().split())
