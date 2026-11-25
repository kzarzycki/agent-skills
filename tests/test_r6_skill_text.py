"""The lines that name what the merge queue's batch check runs say R6 with its floor and point at the rule, and the R6
bullet holds the floor, the refusal, the fallback and the batching (#2178)."""

from __future__ import annotations

import re
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "loop" / "skills" / "engineering-loop"
OLD = "only the tests the batch's PRs affect"
POINTER = (
    "only what R6 selects, the unkeyed checks and the cross-change tests with the floor"
    " (A check runs only if it can fail because of the change"
)


def text(name: str) -> str:
    return " ".join((LOOP / name).read_text().split())


def test_no_line_still_says_the_batch_runs_every_test_its_prs_affect() -> None:
    for name in ("SKILL.md", "lead.md"):
        assert OLD not in text(name), name


def test_the_queue_lines_point_at_the_rule_section() -> None:
    assert text("SKILL.md").count(POINTER) == 5
    assert text("lead.md").count(POINTER) == 1


def test_the_r6_bullet_holds_the_floor_the_refusal_the_fallback_and_the_batching() -> None:
    [bullet] = re.findall(r"- \*\*R6\.[^\n]*", (LOOP / "SKILL.md").read_text())
    for part in (
        "`select.unkeyed` checks",
        "The floor: a PR in the entry with no record for its tree (R1) of loop.md's `Affected tests:` command",
        "a record of the gate alone proves no test",
        "the local queue's `land`, which no queue run tests, refuses a head with no record of that same `Affected tests:` run",
        "naming the `affected-tests --record` that makes one",
        "an empty set passes only when every PR has a record",
        "is refused",
        "a path that skips that step merges nothing and says why",
        "falls back to the entry's affected tests, saying so and why",
        "`land` block (`batch_size`, `batch_wait_seconds`)",
        "`approvals.py queue-config`",
        "The local queue runs no test today and stays so.",
    ):
        assert part in bullet, part


def test_no_skill_line_says_a_run_that_cant_tell_runs_or_records_nothing() -> None:
    """After #2217 a run that can't tell never runs nothing, and a `--record` run records against the merge base
    (#2361): the skill text must not drift back to the old rule."""
    for name in ("SKILL.md", "worker.md"):
        assert "or can't tell records nothing" not in text(name), name
    worker = text("worker.md")
    assert (
        "a run that fails records nothing, nor does a run with no `Affected tests:` line" in worker
    )
    skill = text("SKILL.md")
    assert "never nothing for a change it can't classify" in skill
    assert "A selection over half the suite runs as picked (#1872)" in skill
