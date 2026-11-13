from __future__ import annotations

import re
from pathlib import Path

import yaml

REPOSITORY = Path(__file__).resolve().parents[1]
NOTE = REPOSITORY / "docs/layers.md"
# Tooling sits below the stack: it names nothing in it, and any skill may name it.
TOOLING = -1


def layer_map(note: Path) -> dict:
    """The note's fenced YAML block that holds `skills:`."""
    for block in re.findall(r"^```yaml\n(.*?)^```", note.read_text(), re.MULTILINE | re.DOTALL):
        data = yaml.safe_load(block)
        if isinstance(data, dict) and "skills" in data:
            return data
    raise AssertionError(f"{note}: no yaml block with `skills:`")


def skills(root: Path) -> dict[str, Path]:
    # Plugin skills only: dot directories hold generated copies.
    found: dict[str, Path] = {}
    for path in sorted(root.glob("*/skills/*/SKILL.md")):
        if path.parts[len(root.parts)].startswith("."):
            continue
        assert path.parent.name not in found, f"two skills named {path.parent.name}"
        found[path.parent.name] = path.parent
    return found


def mention(name: str) -> re.Pattern[str]:
    if "-" in name:
        return re.compile(rf"(?<![\w.-]){re.escape(name)}(?![\w-])")
    # A one-word name is often a plain word (`pr`, `implement`), so only a reference to the skill counts.
    word = re.escape(name)
    return re.compile(rf"`/?{word}`|(?<![\w.-]){word} skill\b|/{word}/")


def problems(root: Path, data: dict) -> list[str]:
    found = skills(root)
    entries = data["skills"]
    rank = {
        name: TOOLING if entry["layer"] == "tooling" else entry["layer"]
        for name, entry in entries.items()
    }
    out = [f"{name}: no layer in the map" for name in found if name not in entries]
    out += [f"{name}: in the map, but no such skill" for name in entries if name not in found]
    out += [
        f"{name}: only an adapter (layer 0) implements a port"
        for name, entry in entries.items()
        if entry.get("implements") and entry["layer"] != 0
    ]
    upward: set[str] = set()
    for skill, folder in found.items():
        if skill not in rank:
            continue
        above = [name for name in found if name in rank and rank[name] > rank[skill]]
        for file in folder.rglob("*"):
            if not file.is_file() or "__pycache__" in file.parts:
                continue
            text = file.read_text(errors="ignore")
            upward |= {f"{skill} -> {name}" for name in above if mention(name).search(text)}
    implemented = {
        f"{name} -> {port}"
        for name, entry in entries.items()
        for port in entry.get("implements", [])
    }
    out += [f"{pair}: stale implements, remove it" for pair in sorted(implemented - upward)]
    upward -= implemented
    exceptions = data.get("exceptions") or {}
    out += [f"{pair}: names a higher layer" for pair in sorted(upward - exceptions.keys())]
    out += [f"{pair}: stale exception, remove it" for pair in sorted(exceptions.keys() - upward)]
    return out


def test_no_skill_names_a_layer_above_its_own() -> None:
    assert problems(REPOSITORY, layer_map(NOTE)) == []


def test_the_check_sees_the_plugins() -> None:
    assert {"engineering-loop", "tdd", "find-conversation"} <= skills(REPOSITORY).keys()


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


MAP = {"skills": {"loop": {"layer": 3}, "craft": {"layer": 1}}}


def test_an_upward_mention_is_flagged(tmp_path: Path) -> None:
    tree(
        tmp_path, {"p/skills/loop/SKILL.md": "", "p/skills/craft/SKILL.md": "see the `loop` skill"}
    )
    assert problems(tmp_path, MAP) == ["craft -> loop: names a higher layer"]


def test_a_downward_mention_and_a_plain_word_are_accepted(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {"p/skills/loop/SKILL.md": "uses `craft`", "p/skills/craft/SKILL.md": "a loop of steps"},
    )
    assert problems(tmp_path, MAP) == []


def test_a_stale_exception_is_refused(tmp_path: Path) -> None:
    tree(tmp_path, {"p/skills/loop/SKILL.md": "", "p/skills/craft/SKILL.md": ""})
    stale = {**MAP, "exceptions": {"craft -> loop": {"reason": "gone", "removed_by": "#1"}}}
    assert problems(tmp_path, stale) == ["craft -> loop: stale exception, remove it"]


def test_an_unmapped_skill_is_refused(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {"p/skills/loop/SKILL.md": "", "p/skills/craft/SKILL.md": "", "p/skills/new/SKILL.md": ""},
    )
    assert problems(tmp_path, MAP) == ["new: no layer in the map"]


def test_an_adapter_names_the_port_it_implements(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {"p/skills/craft/SKILL.md": "", "p/skills/adapter/SKILL.md": "../craft/scripts/run.py"},
    )
    data = {"skills": {"craft": {"layer": 1}, "adapter": {"layer": 0, "implements": ["craft"]}}}
    assert problems(tmp_path, data) == []
    data["skills"]["adapter"] = {"layer": 0}
    assert problems(tmp_path, data) == ["adapter -> craft: names a higher layer"]
    tree(tmp_path, {"p/skills/adapter/SKILL.md": ""})
    data["skills"]["adapter"] = {"layer": 0, "implements": ["craft"]}
    assert problems(tmp_path, data) == ["adapter -> craft: stale implements, remove it"]


def test_a_slash_invocation_of_a_one_word_skill_counts(tmp_path: Path) -> None:
    tree(
        tmp_path,
        {"p/skills/loop/SKILL.md": "", "p/skills/craft/SKILL.md": "Use `/loop` to run it."},
    )
    assert problems(tmp_path, MAP) == ["craft -> loop: names a higher layer"]
