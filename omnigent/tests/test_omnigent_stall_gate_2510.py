"""wait-for's stall limit follows a gate run's timeout; claude-cloud-run beats while it works (#2510)."""

import subprocess
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
        lambda: SimpleNamespace(
            tree_policy=lambda root: None,
            timeouts=lambda loop: {"test": 60, "run": run},
            Refused=ValueError,
        ),
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


def gate_log(tmp_path: Path) -> Path:
    log = tmp_path / "gate.log"
    log.write_text("lock /x\nlocked\nbuilding\n")
    return log


def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> Path:
    """A checkout holding ``files``, which is the working directory."""
    root = tmp_path / "proj"
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    monkeypatch.chdir(root)
    return gate_log(tmp_path)


def test_the_real_policy_read_gives_a_gate_run_the_policys_timeouts_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_text = "# Gatekeeper\n\n## Policy\n\n```yaml\ntimeouts:\n  run: 2h\n```\n"
    log = project(tmp_path, monkeypatch, {"docs/agents/gatekeeper.md": policy_text})
    assert omnigent_agent.gate_stall(log, None) == 7200.0


def test_a_policy_with_no_timeouts_gives_the_default_run_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy_text = "# Gatekeeper\n\n## Policy\n\n```yaml\nspec:\n  auto: true\n```\n"
    log = project(tmp_path, monkeypatch, {"docs/agents/gatekeeper.md": policy_text})
    assert omnigent_agent.gate_stall(log, None) == 3600.0


def test_a_loop_md_with_no_settings_block_keeps_the_default_stall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = project(tmp_path, monkeypatch, {"docs/agents/loop.md": "# Loop\n\nGate: make\n"})
    assert omnigent_agent.gate_stall(log, None) is None


def test_an_unexpected_policy_error_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = project(tmp_path, monkeypatch, {})

    def boom(loop: object) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        omnigent_agent,
        "_load_gatekeeper",
        lambda: SimpleNamespace(tree_policy=lambda root: None, timeouts=boom, Refused=ValueError),
    )
    with pytest.raises(RuntimeError, match="boom"):
        omnigent_agent.gate_stall(log, None)
