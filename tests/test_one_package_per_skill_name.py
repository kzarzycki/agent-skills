"""A skill name is shipped by one package (#1731). APM deploys every package's skills into one directory, so a folder
name two packages hold deploys from one of them and the other's files vanish from an install. The only second holder
allowed is a folder of old-path forwarders, which the checkout keeps for one release line (tests/test_old_paths.py)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
FORWARDER_MARK = "only forwards to another skill's script"


def _folders() -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = defaultdict(list)
    for manifest in sorted(REPOSITORY.glob("*/.claude-plugin/plugin.json")):
        for folder in sorted((manifest.parents[1] / "skills").glob("*")):
            if folder.is_dir():
                found[folder.name].append(folder)
    return found


def test_no_skill_name_ships_from_two_packages() -> None:
    twice = {
        name: [str(f.relative_to(REPOSITORY)) for f in folders if (f / "SKILL.md").exists()]
        for name, folders in _folders().items()
    }
    assert {name: held for name, held in twice.items() if len(held) > 1} == {}


def test_a_second_folder_of_one_name_holds_only_forwarders() -> None:
    offenders: list[str] = []
    for folders in _folders().values():
        if len(folders) < 2:
            continue
        for folder in folders:
            if (folder / "SKILL.md").exists():
                continue
            for path in sorted(
                p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts
            ):
                if path.suffix == ".md":
                    continue  # a role doc kept identical to the moved file, held by test_old_paths
                if FORWARDER_MARK not in path.read_text():
                    offenders.append(str(path.relative_to(REPOSITORY)))
    assert offenders == []
