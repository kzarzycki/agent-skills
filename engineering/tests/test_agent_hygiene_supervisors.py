"""agent-hygiene names an `omnigent-supervise-*` user unit that is not active or restarts in a loop, with its last log
line, and says nothing of a healthy one (#2671). `systemctl` and `journalctl` are fakes; names are fake."""

from __future__ import annotations

import time

from test_agent_hygiene_drift import world

NOW = int(time.monotonic() * 1e6)
UNITS = {  # name: (ActiveState, SubState, NRestarts, seconds since it entered that state)
    "omnigent-supervise-looping": ("active", "running", 40, 5),
    "omnigent-supervise-dead": ("failed", "failed", 1, 5000),
    "omnigent-supervise-healthy": ("active", "running", 0, 99999),
    "omnigent-supervise-old": (
        "active",
        "running",
        9,
        99999,
    ),  # many restarts over days: not a loop
}


def fake_systemctl(home):
    blocks = "\n\n".join(
        f"Id={n}.service\nActiveState={a}\nSubState={s}\nNRestarts={r}\n"
        f"ActiveEnterTimestampMonotonic={NOW - age * 10**6}"
        for n, (a, s, r, age) in UNITS.items()
    )
    names = "\n".join(f"{n}.service loaded {a} {s} x" for n, (a, s, _r, _g) in UNITS.items())
    (home / "fakebin" / "systemctl").write_text(
        f"#!/bin/sh\ncase \"$2\" in list-units) cat <<'E'\n{names}\nE\n;; show) cat <<'E'\n{blocks}\nE\n;; esac\n"
    )
    (home / "fakebin" / "journalctl").write_text(
        '#!/bin/sh\necho "exec: /old/forwarder: No such file ($3)"\n'
    )
    for tool in ("systemctl", "journalctl"):
        (home / "fakebin" / tool).chmod(0o755)


def test_a_crash_looping_or_dead_supervisor_unit_is_named_and_a_healthy_one_is_not(
    tmp_path, monkeypatch
):
    _clones, _heads, run, calls, _git = world(tmp_path, monkeypatch, ["acme/managed"])
    fake_systemctl(tmp_path.resolve())
    out = run()
    assert (
        "supervisor unit omnigent-supervise-looping.service is active/running, restarted 40 times"
        in out
    ), out
    assert "omnigent-supervise-dead.service is failed/failed" in out, out
    assert (
        "last log line: exec: /old/forwarder: No such file (omnigent-supervise-looping.service)"
        in out
    ), out
    assert "healthy" not in out and "supervise-old" not in out, out
    told = [text for repo, text in calls if repo is None]
    assert told and "omnigent-supervise-looping" in told[0] and "healthy" not in told[0], calls
    assert "omnigent-supervise-looping" not in "".join(t for _r, t in calls[1:]), calls


def test_each_unit_state_is_told_once(tmp_path, monkeypatch):
    _clones, _heads, run, calls, _git = world(tmp_path, monkeypatch, ["acme/managed"])
    fake_systemctl(tmp_path.resolve())
    run()
    first = len(calls)
    out = run()
    assert "LOOP:" in out and len(calls) == first, (out, calls)
