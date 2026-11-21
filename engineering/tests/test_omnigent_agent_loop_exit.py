"""wait-for ends only on the recipe's own ``loop-exit <pid> <n>`` line, not a command's ``exit 0`` (#1607)."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent

PACK = Path(__file__).resolve().parents[1] / "skills"
OLD_LINE = 'echo "exit $?"'


@pytest.fixture
def live():
    """A live process whose pid a log can name."""
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(omnigent_agent, "WAIT_FOR_EVERY", 0.05)


def write(tmp_path: Path, pid: int, *lines: str) -> Path:
    log = tmp_path / "run.log"
    log.write_text("\n".join([f"run {pid}", *lines]) + "\n")
    return log


def test_live_pid_with_a_command_printed_exit_line_keeps_waiting(tmp_path, live):
    log = write(tmp_path, live.pid, "4 passed", "exit 0")
    assert omnigent_agent.wait_for(log, str(live.pid), None, "checks", 0.3) is None


def test_loop_exit_line_ends_the_wait_with_its_code(tmp_path, live):
    log = write(tmp_path, live.pid, "exit 0", f"loop-exit {live.pid} 0")
    code, text = omnigent_agent.wait_for(log, str(live.pid), None, "checks", 5)
    assert code == 0 and text.startswith("exit 0")
    log = write(tmp_path, live.pid, "1 failed", f"loop-exit {live.pid} 3")
    code, text = omnigent_agent.wait_for(log, str(live.pid), None, "checks", 5)
    assert code == 3 and "1 failed" in text


def test_another_pids_loop_exit_line_is_ignored(tmp_path, live):
    log = write(tmp_path, live.pid, f"loop-exit {live.pid + 1} 0")
    assert omnigent_agent.wait_for(log, str(live.pid), None, "checks", 0.3) is None


def test_gone_pid_with_an_old_style_last_line_still_ends(tmp_path):
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    log = write(tmp_path, done.pid, "4 passed", "exit 3")
    code, text = omnigent_agent.wait_for(log, str(done.pid), None, "checks", 5)
    assert code == 3 and text.startswith("exit 3")


def test_gone_pid_bare_exit_that_is_not_last_is_no_end(tmp_path):
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    log = write(tmp_path, done.pid, "exit 0", "more output")
    code, text = omnigent_agent.wait_for(log, str(done.pid), None, "checks", 5)
    assert code == 1 and text.startswith("gone")


def test_no_copy_of_the_recipe_writes_the_old_exit_line():
    stale = [
        str(p.relative_to(PACK))
        for p in PACK.rglob("*")
        if p.is_file()
        and p.suffix in {".md", ".py", ".sh", ".yml", ".yaml"}
        and OLD_LINE in p.read_text(errors="replace")
    ]
    assert stale == []
