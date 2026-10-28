from __future__ import annotations

import re
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SKILLS = sorted(
    path
    for path in REPOSITORY.glob("*/skills/*/SKILL.md")
    if not path.parts[len(REPOSITORY.parts)].startswith((".", "_"))
)
# The convention's shape, which a host installer reads line by line: a quoted value indented
# under a top-level `metadata:`, holding space-separated `tool` or `tool>=version` entries.
LINE = re.compile(r'  requires: "([^"]*)"')
ENTRY = re.compile(r"[a-z0-9][a-z0-9-]*(>=[0-9]+(\.[0-9]+)*)?")


@pytest.mark.parametrize(
    "skill_md", SKILLS, ids=lambda p: p.parent.relative_to(REPOSITORY).as_posix()
)
def test_declared_requirements_match_the_convention(skill_md: Path) -> None:
    frontmatter = skill_md.read_text().split("\n---\n", 1)[0]
    parent = None
    for line in frontmatter.splitlines()[1:]:
        if re.match(r"[^\s#][^:]*:", line):
            parent = line.split(":", 1)[0]
        if "requires" not in line.split(":", 1)[0]:
            continue
        assert parent == "metadata", f"requires outside metadata: {line!r}"
        match = LINE.fullmatch(line)
        assert match, f"not a quoted `  requires:` line: {line!r}"
        entries = match.group(1).split()
        assert entries, "empty requires"
        bad = [entry for entry in entries if not ENTRY.fullmatch(entry)]
        assert not bad, f"entries not `tool` or `tool>=version`: {bad}"
