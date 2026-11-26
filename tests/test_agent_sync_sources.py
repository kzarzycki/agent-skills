"""The generated agent files match their `.apm` source, and settings.json wires each guard once (#2770).

`apm install` regenerates `.claude/rules/project.md` and `AGENTS.md` from `.apm/instructions/`, so a line added
only to a generated file is dropped by the next install and a session then commits the drift. It also appends a
hook entry that does not equal one already in `.claude/settings.json`, which wired a guard twice.
"""

from __future__ import annotations

import json
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def _body(text: str) -> str:
    """The instruction text without front matter or the generated header and heading."""
    text = text.split("\n---\n", 1)[-1] if text.startswith("---") else text
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(("<!--", "# AGENTS.md", "paths:", '  - "', "## Files matching"))
    ).strip()


def test_generated_instruction_files_hold_every_line_of_their_apm_source() -> None:
    source = _body((REPOSITORY / ".apm/instructions/project.instructions.md").read_text())
    source = "\n".join(
        ln for ln in source.splitlines() if not ln.startswith(("description:", "applyTo:"))
    )
    for generated in (".claude/rules/project.md", "AGENTS.md"):
        text = (REPOSITORY / generated).read_text()
        lines = [ln for ln in _body(text).splitlines() if ln.strip()]
        assert lines == [ln for ln in source.splitlines() if ln.strip()], (
            f"{generated} differs from its .apm source (edit the source, run mise run agent-sync)"
        )


def test_settings_wires_each_hook_command_once() -> None:
    settings = json.loads((REPOSITORY / ".claude/settings.json").read_text())
    commands = [
        hook["command"]
        for event in settings.get("hooks", {}).values()
        for entry in event
        for hook in entry["hooks"]
    ]
    assert len(commands) == len(set(commands)), f"a hook is wired twice: {commands}"
