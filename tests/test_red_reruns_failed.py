"""What a red reruns, in the skill's lines (#2177): R5 states both cases and the gatekeeper verb that makes the rerun,
no line reruns the failed tests alone on an unchanged tree, and a red queue entry's whole rerun is named as a gap against
R5 with the issues that close it, so a lead neither trusts the whole rerun nor expects a rerun the tools don't make."""

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
    assert "R5 rules out" in step and "only where its own CI calls `rerun-tests`" in step
    assert not any(issue in step for issue in GAP)
    assert "read the red's log at once" in step


def test_r5_states_both_reruns_and_the_verb_that_makes_them():
    skill = (SKILL / "SKILL.md").read_text()
    rule = next(line for line in skill.splitlines() if line.startswith("- **R5."))
    assert "the failed tests plus what the fix reaches" in rule
    assert "the red run's own selection once, in the same order and environment" in rule
    assert "never the failed tests alone on an unchanged tree" in rule and "`Flaky:` issue" in rule
    assert "approvals.py rerun-tests" in rule


def test_no_line_reruns_the_failed_tests_alone():
    for name in ("SKILL.md", "lead.md", "worker.md", "verifier.md"):
        text = (SKILL / name).read_text()
        assert "failed tests only" not in text and "rerun only the failed tests" not in text, name
    skill = (SKILL / "SKILL.md").read_text()
    fallback = skill[skill.index("- **Flaky tests.**") :][:900]
    assert "rerun once by R5" in fallback and "approvals.py rerun-tests" in fallback


def test_no_rerun_or_fix_hides_a_retry_in_the_test():
    """#2177: a sleep, wait loop or retry inside the test would turn the one-rerun exception into a permanent mask."""
    skill = (SKILL / "SKILL.md").read_text()
    rule = next(line for line in skill.splitlines() if line.startswith("- **R5."))
    flaky = skill[skill.index("- **Flaky tests.**") :][:2000]
    for text in (rule, flaky):
        assert "adds a sleep, a wait loop or a retry to the test itself" in text.replace(
            "\n  ", " "
        )
        assert "kzarzycki/agent-skills/issues/1482" in text
