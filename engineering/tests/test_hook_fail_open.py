"""A hook command of the pack whose script is gone must not block a Bash call (#2773).

A PreToolUse hook that exits 2 blocks the call (Claude Code's hooks reference: "Exit code 2 ... blocking
error"), and `python3 <missing file>` exits 2. A consumer that upgrades across a hook move gets, from one `apm
install`, the new entries and the old ones, whose files the same install deleted; so every Bash call was refused.
The pack's commands skip a missing script with a one-line warning and exit 0, and pass the script's own exit code
through when it is there.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

HOOKS_PACKAGE = Path(__file__).resolve().parents[2] / "engineering-hooks"
COMMANDS = [
    hook["command"]
    for entry in json.loads((HOOKS_PACKAGE / "hooks" / "hooks-claude.json").read_text())["hooks"][
        "PreToolUse"
    ]
    for hook in entry["hooks"]
]


def _run(command: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", command],
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(root)},
        input='{"tool_name": "Bash", "tool_input": {"command": "echo hi"}}',
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_pack_ships_three_hook_commands() -> None:
    assert len(COMMANDS) == 3


@pytest.mark.parametrize("command", COMMANDS)
def test_a_command_whose_script_is_missing_exits_zero_with_one_warning(
    command: str, tmp_path: Path
) -> None:
    result = _run(command, tmp_path)
    assert result.returncode == 0, result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert "missing" in result.stderr


@pytest.mark.parametrize("command", COMMANDS)
def test_a_command_passes_its_scripts_exit_code_through(command: str, tmp_path: Path) -> None:
    script = command.split("hooks/")[1].split('"')[0]
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / script).write_text("import sys\nsys.exit(2)\n")
    assert _run(command, tmp_path).returncode == 2  # a real block still blocks
