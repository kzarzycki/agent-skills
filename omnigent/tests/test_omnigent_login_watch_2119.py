"""``supervise`` watches the Omnigent login (#2119): ``omnigent login-status --live`` once an hour and the host's
``host_auth_rejected.json``, one USER NEEDED alert per change of state, the return to ok noted once."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_omnigent_agent import omnigent_agent as oa

SERVER = "https://omni.example"


class Rig:
    """A fake ``omnigent`` answering ``login-status``, plus the alerts and notes the watch raised."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.code, self.err, self.raises, self.runs = 0, "", None, []
        self.alerts: list[tuple[str, str]] = []
        self.notes: list[tuple[object, str | None]] = []
        self.memo: dict = {}
        self.data = tmp_path
        monkeypatch.setattr(oa.subprocess, "run", self.run)

    def run(self, cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        self.runs.append(cmd)
        if self.raises:
            raise self.raises
        out = json.dumps({"state": "x", "reason": "grant ends soon", "access_expires_in": 1})
        return subprocess.CompletedProcess(cmd, self.code, out, self.err)

    def watch(self, now: float) -> None:
        oa.login_watch(
            SERVER,
            self.memo,
            now,
            lambda eid, line: self.alerts.append((eid, line)),
            lambda k, m: self.notes.append((k, m)),
            self.data,
        )

    def reject(self, on: bool) -> None:
        f = self.data / "host_auth_rejected.json"
        f.write_text(json.dumps({"since": 1.0, "streak": 5, "fix": "x"})) if on else f.unlink()


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Rig:
    return Rig(monkeypatch, tmp_path)


def test_runs_live_status_of_its_server_and_stays_quiet_when_ok(rig: Rig) -> None:
    rig.watch(0)
    assert rig.runs == [["omnigent", "login-status", SERVER, "--live", "--json"]]
    assert rig.alerts == [] and rig.notes == [("login-cli", None)]


@pytest.mark.parametrize(("code", "word"), [(1, "expiring"), (2, "cannot-renew")])
def test_exit_one_and_two_alert_naming_the_login_command(rig: Rig, code: int, word: str) -> None:
    rig.code = code
    rig.watch(0)
    [(eid, line)] = rig.alerts
    assert eid.startswith(f"login:{word}:")
    assert line.startswith("USER NEEDED:") and f"`omnigent login {SERVER}`" in line
    assert "grant ends soon" in line


def test_rejection_file_alerts_without_running_the_cli_again(rig: Rig) -> None:
    rig.watch(0)
    rig.reject(True)
    rig.watch(60)  # inside the hour: the file is read, the CLI is not run
    assert len(rig.runs) == 1
    [(eid, line)] = rig.alerts
    assert eid.startswith("login:rejected:") and "rejected" in line


def test_one_alert_per_change_not_per_hour(rig: Rig) -> None:
    rig.code = 1
    for hour in range(4):
        rig.watch(hour * oa.LOGIN_POLL)
    assert len(rig.runs) == 4 and len(rig.alerts) == 1
    rig.code = 2  # a change of state alerts again
    rig.watch(4 * oa.LOGIN_POLL)
    assert len(rig.alerts) == 2 and "cannot-renew" in rig.alerts[1][1]


def test_return_to_ok_is_noted_once_and_a_new_problem_alerts_again(rig: Rig) -> None:
    rig.code = 2
    rig.watch(0)
    rig.code = 0
    rig.watch(oa.LOGIN_POLL)
    rig.watch(2 * oa.LOGIN_POLL)
    back = [n for n in rig.notes if n[0] == "login-ok" and n[1]]
    assert len(back) == 1 and "ok again" in back[0][1]
    rig.code = 1
    rig.watch(3 * oa.LOGIN_POLL)
    assert len(rig.alerts) == 2


def test_missing_binary_is_noted_once_and_never_alerts(rig: Rig) -> None:
    rig.raises = FileNotFoundError("omnigent")
    rig.watch(0)
    rig.watch(oa.LOGIN_POLL)
    assert rig.alerts == []
    assert [n[1] for n in rig.notes if n[1]] == [
        "omnigent is not on PATH: its login is not watched"
    ] * 2
    # the real log() prints a repeated message once


def test_older_cli_without_login_status_is_not_an_alert(rig: Rig) -> None:
    rig.code, rig.err = 2, "Error: No such command 'login-status'."
    rig.watch(0)
    assert rig.alerts == []
    assert any("no login-status" in (n[1] or "") for n in rig.notes)


def test_rejection_file_still_alerts_beside_an_older_cli(rig: Rig) -> None:
    rig.code, rig.err = 2, "Error: No such command 'login-status'."
    rig.reject(True)
    rig.watch(0)
    assert len(rig.alerts) == 1 and "rejected" in rig.alerts[0][1]


def test_data_dir_comes_from_the_environment(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "host_auth_rejected.json").write_text("{}")
    monkeypatch.setenv("OMNIGENT_DATA_DIR", str(other))
    oa.login_watch(
        SERVER, rig.memo, 0, lambda e, line: rig.alerts.append((e, line)), lambda k, m: None
    )
    assert len(rig.alerts) == 1


def test_login_event_routes_to_the_owner() -> None:
    assert oa.route({"kind": "login"}, lambda: ("none", ""))[1] == "owner"
