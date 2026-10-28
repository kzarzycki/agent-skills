"""The vendoring routine is a method: each project rule is a slot, and this repository's values
for every slot live with the engineering package, not in the reusable skill."""

from __future__ import annotations

import re
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
ROUTINE = REPOSITORY / "vendoring" / "skills" / "vendoring" / "ROUTINE.md"
VALUES = REPOSITORY / "engineering" / "MAINTENANCE.md"
# What only this repository decides: its pack, upstream, owner, tasks, checks, merge and tags.
THIS_REPOSITORY = ("engineering", "mattpocock", "kzarzycki", "mise ", "qualify", "--squash", "gh ")


def _slots(text: str) -> list[str]:
    return re.findall(r"^- \*\*(.+?)\*\*:", text.split("\n## ", 1)[0], flags=re.MULTILINE)


def test_the_routine_states_no_project_rule() -> None:
    text = ROUTINE.read_text()
    assert [word for word in THIS_REPOSITORY if word in text] == []


def test_this_repository_fills_every_slot_of_the_routine() -> None:
    slots = _slots(ROUTINE.read_text())
    assert len(slots) == 8
    values = re.findall(r"^- \*\*(.+?)(?::\*\*|\*\*)", VALUES.read_text(), flags=re.MULTILINE)
    assert [slot for slot in slots if slot not in values] == []
