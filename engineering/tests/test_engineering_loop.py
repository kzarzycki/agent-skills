"""The engineering loop is method: a project's facts live in its own docs/agents/ files, never in the skill."""

from __future__ import annotations

import re
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop"
# Terms of the project the loop was ported from; `ta/` only as a path start, so `data/` is no hit.
PROJECT_TERMS = re.compile(r"(?<![\w.-])ta/|bin/dev|IBKR|trinity", re.IGNORECASE)


def hits(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root)}:{number}: {line.strip()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1)
        if PROJECT_TERMS.search(line)
    ]


def test_the_loop_names_no_project() -> None:
    assert LOOP.is_dir() and hits(LOOP) == []


def test_the_check_catches_each_term_but_not_a_lookalike(tmp_path: Path) -> None:
    lines = ["run ta/x", "bin/dev up", "IBKR fills", "Trinity's", "~/dev/trinity", "data/ meta/"]
    (tmp_path / "f.md").write_text("\n".join(lines))
    assert [hit.split(": ", 1)[1] for hit in hits(tmp_path)] == lines[:-1]


def loop_sections() -> list[str]:
    """Section names in SKILL.md's docs/agents/loop.md row, up to the sentence on optional lines."""
    row = next(
        line
        for line in (LOOP / "SKILL.md").read_text().splitlines()
        if line.startswith("| `docs/agents/loop.md` |")
    )
    cell = row.split("|")[2].split(". ")[0]
    return [re.sub(r"\(.*?\)", "", part).split(",")[0].strip() for part in cell.split(";")]


def test_every_cited_loop_section_is_listed() -> None:
    sections = loop_sections()
    assert "Approvals" in sections and "Practice" in sections
    unlisted = [
        f"{path.relative_to(LOOP)}: § {cited}"
        for path in sorted(LOOP.rglob("*.md"))
        for cited in re.findall(
            r"loop\.md`? § (\S+(?: \S+){0,3})", " ".join(path.read_text().split())
        )
        if not any(re.match(rf"{re.escape(name)}\b", cited) for name in sections)
    ]
    assert unlisted == []
