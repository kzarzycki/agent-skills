from __future__ import annotations

from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
# Plugin skills only: dot directories hold generated copies, _attic is not loaded.
SKILLS = sorted(
    path.parent
    for path in REPOSITORY.glob("*/skills/*/SKILL.md")
    if not path.parts[len(REPOSITORY.parts)].startswith((".", "_"))
)
# Harness metadata, attribution and the skill's own tests are not read by the model.
UNREAD_DIRECTORIES = {"agents", "test", "tests"}
UNREAD_NAMES = {"CREDITS.md", "LICENSE", "LICENSE.md", "LICENSE.txt"}


def unreferenced(skill: Path) -> list[str]:
    """Files no pointer chain from SKILL.md reaches, since no harness preloads them."""
    files = {
        path.relative_to(skill)
        for path in skill.rglob("*")
        if path.is_file()
        and path.parts[len(skill.parts)] not in UNREAD_DIRECTORIES
        and path.name not in UNREAD_NAMES
    }
    reached = {Path("SKILL.md")}
    frontier = [Path("SKILL.md")]
    while frontier:
        text = (skill / frontier.pop()).read_text(errors="ignore")
        for path in files - reached:
            names = {path.as_posix(), path.name}
            names |= {
                Path(*path.parts[:depth]).as_posix() + "/" for depth in range(1, len(path.parts))
            }
            if any(name in text for name in names):
                reached.add(path)
                frontier.append(path)
    return sorted(path.as_posix() for path in files - reached)


def test_the_check_sees_the_plugins() -> None:
    assert Path("engineering/skills/code-review") in {s.relative_to(REPOSITORY) for s in SKILLS}


@pytest.mark.parametrize(
    "skill", SKILLS, ids=lambda skill: skill.relative_to(REPOSITORY).as_posix()
)
def test_every_skill_file_is_reachable_from_skill_md(skill: Path) -> None:
    assert unreferenced(skill) == [], "name each file in SKILL.md, or in a file it points to"
