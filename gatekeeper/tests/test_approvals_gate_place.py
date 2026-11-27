"""approvals.py local-ci --place: the gate goes to the Placement host with a free slot and the lowest load (#1139)."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest
from approvals_harness import approvals

# a stand-in for omnigent_agent.py: gate-host answers `$CHOOSE`, gate-run records its argv and exits `$RUN_EXIT`
AGENT = """\
import os, sys
cmd = sys.argv[1]
with open(os.environ["CALLS"], "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
if cmd == "gate-host":
    print(os.environ["CHOOSE"])
else:
    sys.exit(int(os.environ["RUN_EXIT"]))
"""


@pytest.fixture
def agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "omnigent_agent.py"
    script.write_text(AGENT)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls"
    monkeypatch.setenv("CALLS", str(calls))
    monkeypatch.setenv("RUN_EXIT", "7")
    monkeypatch.setattr(approvals, "agent_script", lambda: script)
    monkeypatch.setattr(approvals, "toplevel", lambda: tmp_path)
    monkeypatch.setattr(approvals, "project", lambda **kw: (None, "loop"))
    monkeypatch.setattr(approvals, "settings", lambda loop: {"gate_exclude_hosts": ["node-keep"]})
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "approvals.py")])
    return calls


def test_a_host_with_a_free_slot_runs_the_gate_and_its_exit_code_is_returned(
    agent: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHOOSE", "PICK node-b far")
    code = approvals.placed_gate(["local-ci", "--record", "--place"])
    assert code == 7
    chooser, run = agent.read_text().splitlines()
    assert chooser == "gate-host --exclude=node-keep"  # the policy's list reaches the chooser
    assert run.startswith("gate-run --host node-b --checkout ")
    assert run.endswith(
        "-- uv run approvals.py local-ci --record"
    )  # the same command there, with no --place
    assert "gate placed on node-b" in capsys.readouterr().err


def test_with_no_host_readable_the_gate_stays_here_and_one_line_says_why(
    agent: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHOOSE", "STAY node-a: gate slots not readable; node-b: offline")
    assert approvals.placed_gate(["local-ci", "--record", "--place"]) is None
    err = capsys.readouterr().err.strip().splitlines()
    assert err == ["local-ci: gate stays here: node-a: gate slots not readable; node-b: offline"]
    assert agent.read_text().count("gate-run") == 0


def test_a_run_on_the_picked_host_that_gives_no_result_leaves_the_gate_here(
    agent: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CHOOSE", "PICK node-b far")
    monkeypatch.setenv("RUN_EXIT", "125")
    assert approvals.placed_gate(["local-ci", "--record", "--place"]) is None
    assert "gate stays here: the run on node-b gave no result" in capsys.readouterr().err


def test_a_pick_of_this_host_runs_the_gate_here(
    agent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CHOOSE", "PICK node-here here")
    assert approvals.placed_gate(["local-ci", "--record", "--place"]) is None
    assert "gate-run" not in agent.read_text()


def test_a_held_slot_names_its_holder_so_another_host_reads_it_as_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("GATE_SLOTS", "2")
    monkeypatch.delenv(approvals.SLOT_HELD, raising=False)
    fd, path = approvals.take_slot()
    try:
        assert Path(path).read_text().strip() == str(os.getpid())
    finally:
        os.close(fd)
