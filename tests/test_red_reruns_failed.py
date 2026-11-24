"""A red queue entry's whole rerun is named as a gap against R5, with the issues that close it, in the lines that
describe it (#2177): the skill text says what the tools do today and what the rule asks, so a lead neither trusts the
whole rerun nor expects a failed-tests-only rerun the tools don't make."""

from __future__ import annotations

from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "loop" / "skills" / "engineering-loop"
RULE = "A check runs only if it can fail because of the change"
GAP = ("kzarzycki/agent-skills/issues/1400", "kzarzycki/agent-skills/issues/1794")


def paragraph(text: str, marker: str) -> str:
    """The blank-line-separated paragraph holding `marker`."""
    (found,) = [block for block in text.split("\n\n") if marker in block]
    return found


def test_the_queue_paragraphs_name_the_whole_rerun_as_a_gap_against_r5():
    skill = (SKILL / "SKILL.md").read_text()
    github_queue = paragraph(skill, "a second red on the same head turns it back to draft")
    assert "R5 rules out" in github_queue and RULE in github_queue
    assert all(issue in github_queue for issue in GAP)
    assert "the same gap against R5" in paragraph(skill, "With `land.queue: mergify`")


def test_lead_reads_a_red_at_once_instead_of_waiting_on_the_rerun():
    lead = (SKILL / "lead.md").read_text()
    step = lead[lead.index("a red is enqueued once more") :][:600]
    assert "R5 rules out" in step and all(issue in step for issue in GAP)
    assert "read the red's log at once" in step
