"""approvals.py check setup: the pack script name must start its path component (#1394)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_approvals_setup_check import (
    FENCED,
    FLOW,
    POLICY,
    WORKFLOW,
    fresh,  # noqa: F401  (autouse fixture)
    repo_with,
    run_setup,
)

OWN_SCRIPTS = [
    "scripts/pr_board.py",
    "scripts/my_labels.py",
    "scripts/my-board.py",
    "scripts/my+board.py",
    "scripts/my@labels.py",
]
PACK_SCRIPTS = [
    "scripts/board.py",
    ".agents/skills/engineering-loop/scripts/approvals.py",
    "-u path/labels.py",
    "board.py",
    "/abs/dir/labels.py",
    "'scripts/gatekeeper.py'",
    '"$ROOT/approvals.py"',
    "${VAR}/board.py",
]


def own_script_files(script: str) -> dict[str, str]:
    """A workflow step and a mise task that each run a bare python on the script."""
    flow = (WORKFLOW % "install: false").replace(
        "mise run loop:approvals merge 1", f"python3 {script} --board"
    )
    return {POLICY: FENCED, "mise.toml": f'[tasks.own]\nrun = "python3 {script}"\n', FLOW: flow}


@pytest.mark.parametrize("script", OWN_SCRIPTS)
def test_a_consumers_own_script_ending_in_a_pack_script_name_is_not_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], script: str
) -> None:
    repo_with(tmp_path, monkeypatch, own_script_files(script))
    assert run_setup(capsys)[0] == 0


@pytest.mark.parametrize("script", PACK_SCRIPTS)
def test_a_bare_python_run_of_a_pack_script_is_still_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], script: str
) -> None:
    # ponytail: the match is by file name, so a consumer script named exactly `board.py` is still read as the
    # pack's; the upgrade is matching the pack's install paths.
    repo_with(tmp_path, monkeypatch, own_script_files(script))
    code, out = run_setup(capsys)
    assert code == 1 and "mise.toml:2" in out and f"{FLOW}:" in out


def test_a_mise_task_running_a_consumers_own_script_is_not_a_pack_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        POLICY: FENCED,
        "mise.toml": '[tasks.own]\nrun = "uv run scripts/pr_board.py"\n',
        FLOW: (WORKFLOW % "install: false").replace("loop:approvals", "own"),
    }
    repo_with(tmp_path, monkeypatch, files)
    assert run_setup(capsys)[0] == 0
