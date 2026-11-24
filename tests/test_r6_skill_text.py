"""The lines that name what the merge queue's batch check runs say R6 and point at the rule, and restate none of it."""

from __future__ import annotations

from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "loop" / "skills" / "engineering-loop"
OLD = "only the tests the batch's PRs affect"
RULE = "A check runs only if it can fail because of the change"


def test_no_line_still_says_the_batch_runs_every_test_its_prs_affect() -> None:
    for name in ("SKILL.md", "lead.md"):
        assert OLD not in " ".join((LOOP / name).read_text().split()), name


def test_the_queue_lines_point_at_the_rule_section_and_the_batch_selector() -> None:
    text = " ".join((LOOP / "SKILL.md").read_text().split())
    assert (
        text.count(
            "cross-change tests (R6, A check runs only if it can fail because of the change)"
        )
        >= 4
    )
