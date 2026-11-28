"""GitHub ends a table cell at every unescaped pipe, even inside backticks, so a row with a raw `|` in its text has
more cells than the table's header and loses the rest of the row (#2830)."""

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "SKILL.md"
CELL_BREAK = re.compile(r"(?<!\\)\|")


def test_every_loop_md_row_of_the_skills_table_has_as_many_cells_as_its_header() -> None:
    lines = SKILL.read_text().splitlines()
    rows = [(at, line) for at, line in enumerate(lines) if "docs/agents/loop.md" in line]
    table_rows = [(at, line) for at, line in rows if line.startswith("|")]
    assert table_rows, "no table row names docs/agents/loop.md"
    for at, line in table_rows:
        start = at
        while start > 0 and lines[start - 1].startswith("|"):
            start -= 1
        header = lines[start]
        assert len(CELL_BREAK.findall(line)) == len(CELL_BREAK.findall(header)), (
            f"SKILL.md line {at + 1}: a raw | in the row splits its cell; escape it or reword"
        )
