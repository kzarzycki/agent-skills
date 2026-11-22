"""wait-for ends only on the recipe's own ``loop-exit <pid> <n>`` line, not a command's ``exit 0`` (#1607)."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "loop/skills/engineering-loop/verifier.md"
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
        str(p.relative_to(ROOT))
        for skills in ROOT.glob("[!.]*/skills")
        for p in skills.rglob("*")
        if p.is_file()
        and p.suffix in {".md", ".py", ".sh", ".yml", ".yaml"}
        and OLD_LINE in p.read_text(errors="replace")
    ]
    assert stale == []


def test_recipe_end_line_survives_an_unterminated_last_output_line(tmp_path):
    """The recipe's own end step, taken from verifier.md, run after output with no final newline."""
    step = re.search(
        r"(printf \"\\nloop-exit \$\$ \$\?\\n\" >> <log>)",
        VERIFIER.read_text(),
    )
    assert step, "verifier.md's recipe no longer ends with the fresh-line loop-exit step"
    for status in (0, 3):
        log = tmp_path / f"run{status}.log"
        pid = tmp_path / f"pid{status}"
        end = step[1].replace("<log>", str(log))
        subprocess.run(
            [
                "sh",
                "-c",
                f'echo $$ > {pid}; echo "run $$" > {log}; sh -c "printf done; exit {status}" >> {log} 2>&1; {end}',
            ],
            check=True,
        )
        out = omnigent_agent.wait_for(log, str(pid), None, "checks", 5)
        assert out is not None and out[0] == status


def test_cli_progress_never_shows_another_runs_end_line(tmp_path, live, capsys):
    log = write(tmp_path, live.pid, "collecting tests", f"loop-exit {live.pid + 1} 0")
    argv = ["wait-for", "--log", str(log), "--pid", str(live.pid), "--budget", "0.2"]
    assert omnigent_agent.main(argv) == 6
    assert capsys.readouterr().out == "still running\ncollecting tests\n"


def test_a_failing_pid_query_does_not_hide_a_loop_exit_line(tmp_path, live, monkeypatch):
    pidfile = tmp_path / "pid"
    pidfile.write_text(f"{live.pid}\n")
    log = write(tmp_path, live.pid, f"loop-exit {live.pid} 3")

    def denied(_pid):
        raise omnigent_agent.Fail("ps: operation not permitted")

    monkeypatch.setattr(omnigent_agent, "pid_of", denied)
    out = omnigent_agent.wait_for(log, str(pidfile), None, "checks", 5)
    assert out is not None and out[0] == 3


def test_an_exited_unreaped_wrapper_with_a_legacy_last_line_ends_the_wait(tmp_path):
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        os.waitid(
            os.P_PID, child.pid, os.WEXITED | os.WNOWAIT
        )  # exited, still in the process table
        log = write(tmp_path, child.pid, "gate failed", "exit 3")
        out = omnigent_agent.wait_for(log, str(child.pid), None, "checks", 5)
        assert out is not None and out[0] == 3
    finally:
        child.wait()
