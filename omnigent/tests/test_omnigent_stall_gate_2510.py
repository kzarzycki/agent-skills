"""wait-for's stall limit follows a gate run's timeout; claude-cloud-run beats while it works (#2510)."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_omnigent_agent import no_model, no_sleep, omnigent_agent, trusted_folders  # noqa: F401
from test_omnigent_agent_stall import age, detach, fast, gone, wait_for_text  # noqa: F401
from test_omnigent_claude_cloud_run import checkout, cloud  # noqa: F401
from test_omnigent_claude_cloud_run import cloud_run as cloud_run_main


def policy(monkeypatch: pytest.MonkeyPatch, run: int) -> None:
    monkeypatch.setattr(
        omnigent_agent,
        "_load_gatekeeper",
        lambda: SimpleNamespace(timeouts=lambda loop: {"test": 60, "run": run}),
    )


def test_a_gate_run_silent_past_300s_but_within_the_gate_timeout_is_not_killed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy(monkeypatch, 3600)
    log, pidfile, pid = detach(tmp_path, "echo lock /x; echo locked; echo building; sleep 60")
    wait_for_text(log, "building")
    age(log, 400)  # silent past the old fixed 300 s, within timeouts.run
    argv = ["wait-for", "--log", str(log), "--pid", str(pidfile), "--budget", "0.5"]
    assert omnigent_agent.main(argv) == omnigent_agent.LIMIT
    assert not gone(pid)
    age(log, 4000)  # past the gate timeout: hung after all
    assert omnigent_agent.main(argv) == 1
    assert gone(pid)


def test_a_run_that_is_no_gate_run_keeps_the_300s_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy(monkeypatch, 3600)
    log, pidfile, pid = detach(tmp_path, "echo building; sleep 60")
    wait_for_text(log, "building")
    age(log, 400)
    argv = ["wait-for", "--log", str(log), "--pid", str(pidfile), "--budget", "5"]
    assert omnigent_agent.main(argv) == 1
    assert gone(pid)


def test_the_stalled_outcome_names_the_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    log, pidfile, pid = detach(tmp_path, "echo hello; sleep 60")
    wait_for_text(log, "hello")
    argv = ["wait-for", "--log", str(log), "--pid", str(pidfile), "--stall", "1", "--budget", "60"]
    age(log, 5)
    assert omnigent_agent.main(argv) == 1
    first = capsys.readouterr().out.splitlines()[0]
    assert "--stall" in first and "--stall 0" in first
    assert gone(pid)


def test_claude_cloud_run_prints_a_heartbeat_while_the_remote_command_runs(
    checkout: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cloud(monkeypatch, "REPORT\nEXIT: 0\n1 passed")
    monkeypatch.setattr(omnigent_agent, "CLOUD_RUN_HEARTBEAT", 0.05)
    real = omnigent_agent.command

    def slow(argv: list[str], ended: dict) -> int:
        if argv[0] == "run":
            time.sleep(0.4)  # the remote command, longer than the interval
        return real(argv, ended)

    monkeypatch.setattr(omnigent_agent, "command", slow)
    assert cloud_run_main(checkout, "pytest") == 0
    beats = [l for l in capsys.readouterr().out.splitlines() if "still running" in l]
    assert beats and "s elapsed" in beats[0]
