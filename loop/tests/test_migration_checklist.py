"""The checklist that moves a repo onto the loop rule set (#2231): its three steps, the keys a repo states and the
kinds of local copy it deletes are in SKILL.md, so a repo's migration story can name each by its kind."""

from __future__ import annotations

import re
from pathlib import Path

SKILL = Path(__file__).parents[1] / "skills" / "engineering-loop" / "SKILL.md"


def section() -> str:
    text = SKILL.read_text()
    start = text.index("#### Moving a repo onto the rule set")
    end = text.index("\n#### ", start + 1)
    return text[start:end]


def rows(text: str, header: str) -> list[str]:
    """The first cell of each table row under the table whose header starts with `header`."""
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().startswith(header))
    found = []
    for line in lines[first + 2 :]:
        if not line.strip().startswith("|"):
            break
        found.append(line.strip().split("|")[1].strip())
    return found


def test_the_checklist_has_the_three_steps_in_order() -> None:
    text = section()
    steps = [
        "1. **Install the pack at a release tag.**",
        "2. **State the project's facts in `docs/agents/gatekeeper.md`.**",
        "3. **Delete the local copies, by kind.**",
    ]
    assert [text.index(step) for step in steps] == sorted(text.index(step) for step in steps)
    assert "`engineering-v*` tag" in text and "`apm audit`" in text


def test_step_two_names_each_key_a_repo_states() -> None:
    keys = rows(section(), "| Key |")
    assert keys == [
        "`land.queue`",
        "`land` batch keys",
        "`select.layers`",
        "`select.build_inputs`",
        "`select.unkeyed`",
        "`select.shards`",
        "`timeouts`",
    ]
    text = section()
    for line in ("Affected tests: <command>", "Acceptance tests: <command>", "Acceptance budget:"):
        assert line in text


def test_step_three_names_what_replaces_each_kind_of_copy() -> None:
    text = section()
    start = text.index("| Kind |")
    cells = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text[start:].splitlines()[2:]
        if line.strip().startswith("|")
    ]
    assert len(cells) == 10
    assert all(len(row) == 3 and all(row) for row in cells)


def test_step_three_names_each_kind_of_copy() -> None:
    kinds = rows(section(), "| Kind |")
    assert kinds == [
        "Selector",
        "Red rerun",
        "Queue selection",
        "Push run",
        "Nightly",
        "Release or tag run",
        "Hook",
        "Limits",
        "Carry rule",
        "Duplicate skill text",
    ]


def test_a_migrated_repo_keeps_only_its_loop_configuration() -> None:
    text = " ".join(section().split())
    assert (
        "a file that decides when, where or how often a check runs is a loop rule" in text.lower()
    )
    assert re.search(
        r"loop-specific content is the `gatekeeper.md` block and the `Affected tests:`", text
    )
    assert "release tag, the config block and one row per deleted file" in text
