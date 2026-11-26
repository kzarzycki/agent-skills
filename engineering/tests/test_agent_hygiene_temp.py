"""agent-hygiene's sweep of stale scratch directories under the temp folders (#2650)."""

import os
import subprocess
import sys
import time

from test_agent_hygiene_sweep import load

DAY = 86400


def make(root, name, age_days):
    path = root / name
    path.mkdir(parents=True)
    (path / "data").write_text("x" * 100)
    then = time.time() - age_days * DAY
    for item in (path / "data", path):
        os.utime(item, (then, then))
    return path


def test_old_idle_temp_dir_goes_fresh_and_held_open_ones_stay(tmp_path, monkeypatch):
    hygiene = load(tmp_path / "home", monkeypatch, "agent_hygiene_temp")
    root = tmp_path / "tmp"
    old, fresh = make(root, "old", 10), make(root, "fresh", 1)
    held = make(root, "held", 10)
    (root / "file").write_text("a file, not swept")
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys,time; f=open(sys.argv[1]); print('up',flush=True); time.sleep(60)",
            str(held / "data"),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "up"
        run = hygiene.Run(False, tmp_path / "log")
        hygiene.temp_dirs(run, hygiene.processes(), roots=[root])
    finally:
        holder.kill()
        holder.wait()
    log = (tmp_path / "log").read_text()
    assert not old.exists() and f"removed tmp {old}" in log
    assert fresh.exists() and held.exists() and (root / "file").exists()
    assert f"skip tmp {held}: a process has it open" in log
    assert not run.failed


def test_dry_run_reports_and_removes_nothing(tmp_path, monkeypatch):
    hygiene = load(tmp_path / "home", monkeypatch, "agent_hygiene_temp_dry")
    root = tmp_path / "tmp"
    old = make(root, "old", 10)
    run = hygiene.Run(True, tmp_path / "log")
    hygiene.temp_dirs(run, (set(), []), roots=[root])
    assert old.exists() and f"would remove tmp {old}" in (tmp_path / "log").read_text()


def test_another_users_dir_is_kept_and_named(tmp_path, monkeypatch):
    hygiene = load(tmp_path / "home", monkeypatch, "agent_hygiene_temp_uid")
    root = tmp_path / "tmp"
    theirs = make(root, "theirs", 10)
    mine = os.getuid()
    monkeypatch.setattr(hygiene.os, "getuid", lambda: mine + 1)
    run = hygiene.Run(False, tmp_path / "log")
    hygiene.temp_dirs(run, (set(), []), roots=[root])
    assert (
        theirs.exists()
        and f"skip tmp {theirs}: owned by another user" in (tmp_path / "log").read_text()
    )
