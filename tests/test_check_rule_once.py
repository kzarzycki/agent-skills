"""The rule "a check runs only if it can fail because of the change" is stated once, in engineering-loop's
SKILL.md, with its exceptions and R1-R7, and each role file points to it instead of restating it (#2174)."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SKILL = REPOSITORY / "loop" / "skills" / "engineering-loop"
HEADING = "A check runs only if it can fail because of the change"
EXCEPTIONS = (
    "The base moved and the check reads it.",
    "Flaky or time-dependent tests",
    "Environment-dependent checks",
    "Secrets and network",
)
RULES = (
    "R1. Once per tree.",
    "R2. Scope by what the change touches.",
    "R3. Affected tests only, selected by what a test executes.",
    "R4. A fix round runs only what the round's diff reaches.",
    "R5. A red run reruns only what failed, and only once the cause is fixed or shown unrelated.",
    "R6. The merge queue runs only the cross-change check.",
    "R7. After the merge, only a tree nobody tested runs.",
)


def text(name: str) -> str:
    return (SKILL / name).read_text()


def test_skill_states_rule_exceptions_and_rules_once():
    skill = text("SKILL.md")
    assert skill.count(f"#### {HEADING}") == 1
    for phrase in (
        "**A check runs only if it can fail because of this change.**",
        *EXCEPTIONS,
        *RULES,
    ):
        assert skill.count(phrase) == 1, phrase


def test_rule_precedes_and_replaces_the_merge_model_opening():
    skill = text("SKILL.md")
    assert skill.index(f"#### {HEADING}") < skill.index("**Merge model.**")
    assert "A PR's tests run once per tree, by the role that needs them" not in skill


def test_role_files_point_to_the_section_and_restate_no_rule():
    for name in ("worker.md", "verifier.md", "lead.md"):
        body = text(name)
        assert f"SKILL.md, {HEADING}" in body, name
        for rule in RULES:
            assert rule not in body, (name, rule)
        assert not re.search(r"R[1-7]\. ", body), name


def test_flaky_tests_point_to_the_rule():
    skill = text("SKILL.md")
    start = skill.index("- **Flaky tests.**")
    assert HEADING in skill[start : start + 400]


def test_rule_names_no_language_or_runner():
    skill = text("SKILL.md")
    section = skill[skill.index(f"#### {HEADING}") : skill.index("**Merge model.**")]
    found = re.findall(
        r"\b(?:pytest|python|npm|cargo|gradle|maven|jest|go test|mise)\b", section, re.IGNORECASE
    )
    assert not found, found
