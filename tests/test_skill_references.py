from __future__ import annotations

import re
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


# A name counts only as a whole path token: `data.md` is not named by `metadata.md`,
# and `references/` names a folder only when no file name follows it.
BEFORE, AFTER = r"(?<![\w.-])", r"(?![\w-]|\.\w)"


def pointers(path: Path, source_directory: Path) -> list[str]:
    """Patterns that name `path` from a file in `source_directory`."""
    names = {path.as_posix()}
    if path.parent == source_directory:
        names.add(path.name)
    patterns = [BEFORE + re.escape(name) + AFTER for name in names]
    patterns += [
        BEFORE + re.escape(Path(*path.parts[:depth]).as_posix() + "/") + r"(?![\w.-])"
        for depth in range(1, len(path.parts))
    ]
    return patterns


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
        source = frontier.pop()
        text = (skill / source).read_text(errors="ignore")
        for path in files - reached:
            if any(re.search(pattern, text) for pattern in pointers(path, source.parent)):
                reached.add(path)
                frontier.append(path)
    return sorted(path.as_posix() for path in files - reached)


def test_only_whole_names_count(tmp_path: Path) -> None:
    for name, text in {
        "SKILL.md": "Read references/a.md, see metadata.md, run run.sh, open runner/",
        "references/a.md": "Then b.md.",
        "references/b.md": "",
        "references/orphan.md": "",
        "data.md": "",
        "scripts/run.sh": "",
        "runner/src/main.ts": "",
    }.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    assert unreferenced(tmp_path) == ["data.md", "references/orphan.md", "scripts/run.sh"]


def test_the_check_sees_the_plugins() -> None:
    assert Path("engineering/skills/code-review") in {s.relative_to(REPOSITORY) for s in SKILLS}


@pytest.mark.parametrize(
    "skill", SKILLS, ids=lambda skill: skill.relative_to(REPOSITORY).as_posix()
)
def test_every_skill_file_is_reachable_from_skill_md(skill: Path) -> None:
    assert unreferenced(skill) == [], "name each file in SKILL.md, or in a file it points to"
