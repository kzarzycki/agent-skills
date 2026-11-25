from __future__ import annotations

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff"
PM = SKILL / "roles" / "pm.md"


def limits() -> list[str]:
    text = PM.read_text()
    section = text.split("## Hard limits", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- (.+?)(?=\n- |\Z)", section, flags=re.DOTALL | re.MULTILINE)


def test_every_limit_has_its_reason():
    found = limits()
    assert found
    for item in found:
        assert "because" in item, item


def test_the_file_holds_no_project_values():
    text = PM.read_text()
    assert not re.search(r"https?://|\.registry\b|boards/|projects/\w", text)
    assert not re.search(r"\b\d+\s*(GB|leads)\b", text)


def test_skill_names_the_role_file_with_when_to_read():
    skill = (SKILL / "SKILL.md").read_text()
    assert "roles/pm.md" in skill
    assert re.search(r"roles/pm\.md`? when", skill)
