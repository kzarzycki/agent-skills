"""The heavy-run hook also refuses a hand-written poll loop, in a cloud session too (#2623)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "hooks" / "heavy_run_guard.py"
spec = importlib.util.spec_from_file_location("heavy_run_guard_poll", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

CLOUD = {"CLAUDE_CODE_REMOTE": "true"}
POLLS = [
    "while ! grep -q '^EXIT' gate.log; do sleep 30; done",
    "until grep -q '^EXIT' gate.log; do sleep 5; done",
    "while true; do sleep 1; done",
    "(while ! grep -q EXIT gate.log; do sleep 30; done) &",
    "bash -c 'while ! grep -q EXIT gate.log; do sleep 30; done'",
    "sleep 60",
    "sleep 2m && tail gate.log",
]
ALLOWED = [
    "sleep 2",
    "sleep 5 && echo ready",
    "grep -q '^EXIT' gate.log",
    "python3 omnigent_agent.py wait-for --log gate.log --pid gate.pid --budget 570",
    "while ! python3 omnigent_agent.py wait-for --pr 7 --until checks; do :; done",
    "for f in a b; do echo $f; done",
    "echo 'while true; do sleep 30; done'",
]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    loop = tmp_path / "docs" / "agents" / "loop.md"
    loop.parent.mkdir(parents=True)
    loop.write_text("# Loop\n\nCloud worker: claude-cloud, gate test\n")
    return tmp_path


def call(command: str, cwd: Path) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


@pytest.mark.parametrize("command", POLLS)
@pytest.mark.parametrize("env", [CLOUD, {}], ids=["cloud", "host"])
def test_a_hand_written_poll_loop_is_refused_and_names_the_helper(
    repo: Path, command: str, env: dict[str, str]
) -> None:
    code, line = guard.verdict(call(command, repo), env)
    assert code == 2
    assert "wait-for" in line and "--budget 570" in line


@pytest.mark.parametrize("command", ALLOWED)
def test_the_helper_and_a_short_pause_are_allowed(repo: Path, command: str) -> None:
    assert guard.verdict(call(command, repo), CLOUD) == (0, "")


def test_a_repo_that_does_not_run_the_loop_is_left_alone(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert guard.verdict(call(POLLS[0], tmp_path), CLOUD) == (0, "")
