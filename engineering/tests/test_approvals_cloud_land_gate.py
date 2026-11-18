"""approvals.py: `land: gate_on: cloud` gates the batch tree in a cloud session, the host as the fallback (#1033)."""

from __future__ import annotations

import json
import sys
import time as real_time
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import GITHUB_RULE, approvals, git_in, lands  # noqa: F401

TIMEOUT = 100


class Clock:
    """A stubbed `time` for approvals: `sleep` moves `monotonic` by what it is asked, then runs `tick(now)`."""

    def __init__(self) -> None:
        self.now, self.slept, self.tick = 0.0, [], lambda _now: None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert 0 < seconds and sum(self.slept) < 10_000, "the wait never ends"
        self.slept.append(seconds)
        self.now += seconds
        self.tick(self.now)

    def __getattr__(self, name: str) -> Any:
        return getattr(real_time, name)


@pytest.fixture(autouse=True)
def checks_required(monkeypatch: pytest.MonkeyPatch, required: list[str]) -> None:
    monkeypatch.setattr(approvals, "required_checks", lambda _base: {"check"})


@pytest.fixture
def cloud(
    lands: dict[str, Any], refs: dict[str, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """`land` with `gate_on: cloud`. No git push of the cloud route, no cloud session and no real wait happens: `pushes`
    holds each push's refspec, `asked` each tree the session was asked to gate, `ask` the reason a start fails with
    (else it succeeds), and `record(tree)` puts a record branch for `tree` on origin once the clock reaches `at`."""
    clock = Clock()
    monkeypatch.setattr(approvals, "time", clock)
    state: dict[str, Any] = {"pushes": [], "asked": [], "ask": "", "at": 60, "clock": clock}
    real = approvals.git

    def git(*args: str, **kw: Any) -> str:
        if args[:1] == ("push",) and "loop-land" in args[-1]:
            state["pushes"].append(args[-1])
            return ""
        return real(*args, **kw)

    def ask(tree: str) -> str:
        state["asked"].append(tree)
        return state["ask"]

    def record(tree: str) -> None:
        command, _, env = approvals.gate()
        name = approvals.record_name(tree, command)
        refs[name] = {
            "head": "c" * 40,
            "tree": tree,
            "command": command,
            "time": "2026-01-01T00:00:00Z",
            "env": env,
        }

    monkeypatch.setattr(approvals, "git", git)
    monkeypatch.setattr(approvals, "ask_cloud_gate", ask)
    state["ended"] = lambda: False
    monkeypatch.setattr(approvals, "gate_ended", lambda _tree: state["ended"]())
    state["record"] = record
    return state


def policy(lands: dict[str, Any], setting: str) -> None:
    """The base's loop.md with `setting` (a section), committed to origin's main before any PR is opened."""
    work = lands["work"]
    (work / "docs" / "agents" / "loop.md").write_text(
        GITHUB_RULE.replace("```yaml\n", f"```yaml\n{setting}\n", 1)
    )
    git_in(work, "add", "docs")
    git_in(work, "commit", "-q", "-m", "policy")
    git_in(work, "push", "-q", "origin", "HEAD:refs/heads/main")
    git_in(work, "fetch", "-q", "origin")


ON = f"land:\n  gate_on: cloud\n  cloud_gate_timeout_seconds: {TIMEOUT}"


def tree_of_asked(cloud: dict[str, Any]) -> str:
    [tree] = cloud["asked"]
    return tree


def test_a_record_for_the_tree_lets_land_merge_without_a_host_gate(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["clock"].tick = lambda now: (
        cloud["record"](cloud["asked"][0]) if now >= cloud["at"] else None
    )
    code, lines = lands["land"]()
    tree = tree_of_asked(cloud)
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 0), lines
    # the batch commit goes up as loop-land/<tree> and is deleted again
    assert cloud["pushes"][0].endswith(f":refs/heads/loop-land/{tree}")
    assert cloud["pushes"][1] == f":refs/heads/loop-land/{tree}"
    assert any("passed on it before, reused" in line for line in lines), lines
    assert sum(cloud["clock"].slept) >= cloud["at"]


def test_no_record_before_the_timeout_gates_on_the_host_and_lands(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 1), lines
    assert sum(cloud["clock"].slept) == TIMEOUT
    assert any(
        "no cloud gate (no record for the tree within 100 s): gating on this host" in line
        for line in lines
    ), lines
    assert cloud["pushes"][-1] == f":refs/heads/loop-land/{tree_of_asked(cloud)}"


def test_a_tree_that_already_has_its_passes_asks_no_session_and_pushes_nothing(
    lands: dict[str, Any], cloud: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    policy(lands, ON)
    monkeypatch.setattr(approvals, "step_pass", lambda *_a, **_k: {"exit": 0})
    approvals.cloud_gate("a" * 40, "b" * 40)
    assert (cloud["pushes"], cloud["asked"]) == ([], [])


def test_the_timeout_defaults_to_the_measured_gate_with_room_for_the_first_start(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, "land:\n  gate_on: cloud")
    lands["open"](7, {"7.txt": "7\n"})
    assert lands["land"]()[0] == 0
    assert sum(cloud["clock"].slept) == 2400 and approvals.CLOUD_GATE_SECONDS == 2400


def test_a_refused_start_gates_on_the_host_at_once(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["ask"] = "start refused: out of capacity"
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"](), cloud["clock"].slept) == (0, ["7"], 1, [])
    assert any("no cloud gate (start refused: out of capacity)" in line for line in lines), lines


def test_a_record_branch_for_another_tree_never_counts(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["clock"].tick = lambda now: cloud["record"]("f" * 40) if now >= cloud["at"] else None
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 1), lines
    assert sum(cloud["clock"].slept) == TIMEOUT
    assert any("no record for the tree within" in line for line in lines), lines


@pytest.mark.parametrize("setting", ["", "land:\n  gate_on: host"])
def test_gate_on_absent_or_host_changes_nothing(
    lands: dict[str, Any], cloud: dict[str, Any], setting: str
) -> None:
    if setting:
        policy(lands, setting)
    lands["open"](7, {"7.txt": "7\n"})
    code, _ = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 1)
    assert (cloud["pushes"], cloud["asked"], cloud["clock"].slept) == ([], [], [])


def test_the_red_path_takes_the_same_route_for_each_tree_it_gates(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    """A red batch gates each PR alone, again, then the bare base: every one of those goes to the cloud first."""
    policy(lands, ON.replace(str(TIMEOUT), "0"))
    lands["open"](7, {"red.txt": "1\n"})
    code, _ = lands["land"]("7")
    assert code == 1 and lands["merged"]() == []
    # the batch of one (its red run is its first alone), the same PR once more, then the bare base
    assert len(cloud["asked"]) == 3 and len(set(cloud["asked"])) == 2
    assert lands["runs"]() == 3


def test_a_host_only_step_still_runs_on_the_host(
    lands: dict[str, Any], cloud: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    steps = [
        {"name": "unit", "where": "any", "command": "u", "sets": {}, "legacy": False},
        {"name": "apple", "where": "host", "command": "a", "sets": {}, "legacy": False},
    ]
    monkeypatch.setattr(approvals, "gate_plan", lambda *_a: steps)
    monkeypatch.setattr(approvals, "settings", lambda _loop: {"land": {"gate_on": "cloud"}})
    seen: list[str] = []
    monkeypatch.setattr(
        approvals,
        "step_pass",
        lambda _h, _t, step, show=True: seen.append(step["name"]) or {"exit": 0},
    )
    approvals.cloud_gate("a" * 40, "b" * 40)
    assert seen == ["unit"]


FAKE = """import json, pathlib, sys
log = pathlib.Path(sys.argv[0]).with_name("calls.log")
log.open("a").write(json.dumps(sys.argv[1:]) + "\\n")
mode = pathlib.Path(sys.argv[0]).parent.joinpath("mode").read_text()
if (sys.argv[1], mode) in (("relay", "gone"), ("start", "refuse"), ("launch-dir", "nolaunch")):
    print("session-x")  # a refused start may still have printed an id
    print("no capacity", file=sys.stderr)
    sys.exit(4)
if (sys.argv[1], mode) == ("relay", "queued"):
    sys.exit(5)
if (sys.argv[1], mode) == ("start", "hang"):
    import time
    time.sleep(60)
if sys.argv[1] == "status":
    if "|" in mode:  # "<state>|<last message text>"
        state, text = mode.split("|", 1)
        print("session-1 gate: " + state)
        print("last message: " + text)
        sys.exit(0)
    print("session-1 gate: " + ("turn ended" if mode.startswith("ended") else "running"))
    if mode.startswith("ended "):
        print("last message: DONE: " + mode[6:])
    sys.exit(4 if mode == "vanished" else 0)
if sys.argv[1] == "start":
    print("session-" + str(len(log.read_text().splitlines())))
"""


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A clone, and a stand-in for omnigent_agent.py that logs its arguments: `calls()` reads them, `mode` says `gone`
    to make a relay fail."""
    repo, script = tmp_path / "repo", tmp_path / "scripts" / "omnigent_agent.py"
    script.parent.mkdir()
    script.write_text(FAKE)
    (script.parent / "mode").write_text("up")
    repo.mkdir()
    git_in(repo, "init", "-q")
    git_in(repo, "remote", "add", "origin", "https://example.invalid/acme/app.git")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(approvals, "agent_script", lambda: script)
    return {
        "repo": repo,
        "mode": lambda text: (script.parent / "mode").write_text(text),
        "calls": lambda: [
            json.loads(line) for line in (script.parent / "calls.log").read_text().splitlines()
        ],
    }


def test_one_standing_session_is_started_once_and_messaged_for_later_batches(
    session: dict[str, Any],
) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    assert approvals.ask_cloud_gate("t2") == ""
    first, second, third = session["calls"]()
    assert (first[0], second[0], third[:2]) == ("launch-dir", "start", ["relay", "session-2"])
    assert "loop-land/t1" in second[3] and "loop-land/t2" in third[2]
    # the cloud VM has its own skill install: the brief names no path or interpreter of this host
    assert "uv run <engineering-loop skill>/scripts/approvals.py local-ci --record" in second[3]
    assert sys.executable not in second[3] and str(Path(approvals.__file__).parent) not in second[3]
    kept = json.loads((session["repo"] / ".git" / "approvals" / "cloud-gate.json").read_text())
    assert kept["session"] == "session-2"


def test_a_session_that_is_gone_is_replaced(session: dict[str, Any]) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    session["mode"]("gone")
    assert approvals.ask_cloud_gate("t2") == ""
    calls = session["calls"]()
    # the dropped session is closed, with the launch dir it held; the replacement's launch dir is a new name
    assert [call[0] for call in calls] == [
        "launch-dir",
        "start",
        "relay",
        "launch-dir",
        "start",
        "reap",
    ]
    assert calls[-1][1] == "session-2"
    first, second = calls[0][-1], calls[3][-1]
    assert (
        Path(first).name != Path(second).name and not Path(first).exists() and Path(second).exists()
    )


def test_replacements_never_reuse_a_launch_branch_name(session: dict[str, Any]) -> None:
    """launch-dir makes the branch `launch/<dir name>` in this clone, so a repeated name fails the second one."""
    names = set()
    for _ in range(3):
        session["mode"]("gone")
        assert approvals.ask_cloud_gate("t1") == ""
    names = {Path(c[-1]).name for c in session["calls"]() if c[0] == "launch-dir"}
    assert len(names) == 3


def test_a_session_mid_turn_takes_the_message_queued_and_is_not_replaced(
    session: dict[str, Any],
) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    session["mode"]("queued")
    assert approvals.ask_cloud_gate("t2") == ""
    assert [call[0] for call in session["calls"]()] == ["launch-dir", "start", "relay"]


def test_a_start_that_times_out_leaves_no_launch_dir_and_says_why(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    session["mode"]("hang")
    real = approvals.run_agent
    monkeypatch.setattr(approvals, "run_agent", lambda *a, **k: real(*a, **{**k, "seconds": 1}))
    with pytest.raises(approvals.subprocess.TimeoutExpired):
        approvals.ask_cloud_gate("t1")
    [made] = [c for c in session["calls"]() if c[0] == "launch-dir"]
    assert not Path(made[-1]).exists()


def test_a_session_whose_turn_ended_or_is_gone_reads_as_ended(session: dict[str, Any]) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    assert not approvals.gate_ended("t1")
    for mode in ("ended", "vanished"):
        session["mode"](mode)
        assert approvals.gate_ended("t1") == "ended", mode


def test_only_a_red_line_for_this_tree_reads_as_red(session: dict[str, Any]) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    for mode, kind in (
        ("ended red t1", "red"),
        ("ended red t12", "ended"),
        ("ended red t2", "ended"),
        ("ended red", "ended"),
        ("ended recorded t1", "ended"),
    ):
        session["mode"](mode)
        assert approvals.gate_ended("t1") == kind, mode


def test_a_message_never_passes_for_a_state(session: dict[str, Any]) -> None:
    """Only status's first line names the state: the last message is the model's text, stale on a new turn."""
    assert approvals.ask_cloud_gate("t1") == ""
    for mode in (
        "running|pytest step: failed",
        "running|turn ended: yes",
        "running|session: archived",
        "running|DONE: red t1 (pytest: failed)\nDONE: red t1",
    ):
        session["mode"](mode)
        assert approvals.gate_ended("t1") == "", mode
    session["mode"](
        "failed|DONE: red t1"
    )  # a failed session's last message may be an earlier turn's red line
    assert approvals.gate_ended("t1") == "ended"
    session["mode"]("failed|pytest step: failed")  # a failed state is read from the first line
    assert approvals.gate_ended("t1") == "ended"


def test_the_brief_names_the_tree_on_a_red_line_and_machine_exit_is_not_red(
    session: dict[str, Any],
) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    [task] = [c[3] for c in session["calls"]() if c[0] == "start"]
    assert "`DONE: red t1`" in task and "`machine_exit`" in task and "not red" in task


def test_a_session_that_ended_without_a_record_falls_back_before_the_timeout(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    """A red cloud gate pushes no record: land must not wait the whole timeout for it."""
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["ended"] = lambda: cloud["clock"].now >= 40
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 1), lines
    assert sum(cloud["clock"].slept) < TIMEOUT
    assert any("ended its turn without a record" in line for line in lines), lines


def test_a_red_line_for_the_tree_fails_it_at_once_with_no_host_gate(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["ended"] = lambda: "red" if cloud["clock"].now >= 40 else ""
    code, lines = lands["land"]()
    assert (lands["merged"](), lands["runs"]()) == ([], 0), lines
    assert any("the cloud gate ran red" in line for line in lines), lines
    assert code == 1 and lands["lock"]() == "", lines


def test_a_record_that_lands_as_the_turn_ends_still_counts(
    lands: dict[str, Any], cloud: dict[str, Any]
) -> None:
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    cloud["ended"] = lambda: cloud["clock"].now >= 60
    cloud["clock"].tick = lambda now: cloud["record"](cloud["asked"][0]) if now >= 60 else None
    code, lines = lands["land"]()
    assert (code, lands["merged"](), lands["runs"]()) == (0, ["7"], 0), lines


@pytest.mark.parametrize("kind", ["red", "ended"])
@pytest.mark.parametrize("then", ["running", "record"])
def test_one_ended_read_neither_fails_the_tree_nor_falls_back(
    lands: dict[str, Any], cloud: dict[str, Any], kind: str, then: str
) -> None:
    """A session just messaged can read idle once; only a second read running counts."""
    policy(lands, ON)
    lands["open"](7, {"7.txt": "7\n"})
    reads = iter([kind])
    cloud["ended"] = lambda: next(reads, "")
    if then == "record":
        cloud["clock"].tick = lambda now: cloud["record"](cloud["asked"][0]) if now >= 60 else None
    code, lines = lands["land"]()
    merged, runs = lands["merged"](), lands["runs"]()
    assert not any("ran red" in line or "ended its turn" in line for line in lines), lines
    if then == "record":
        assert (code, merged, runs) == (0, ["7"], 0), lines
    else:  # the session kept running with no record: the timeout, not the read, sends it to the host
        assert sum(cloud["clock"].slept) >= TIMEOUT and (code, merged, runs) == (0, ["7"], 1), lines


def test_a_start_that_fails_says_why(
    session: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "agent_script", lambda: session["repo"] / "missing.py")
    assert "is not installed" in approvals.ask_cloud_gate("t1")


@pytest.mark.parametrize(
    ("mode", "said"),
    [("refuse", "start refused: no capacity"), ("nolaunch", "no launch dir: no capacity")],
)
def test_a_refused_launch_or_start_says_why_and_keeps_no_session(
    session: dict[str, Any], mode: str, said: str
) -> None:
    session["mode"](mode)
    assert approvals.ask_cloud_gate("t1") == said
    assert not (session["repo"] / ".git" / "approvals" / "cloud-gate.json").exists()
    calls = session["calls"]()
    made = Path(next(c for c in calls if c[0] == "launch-dir")[-1])
    assert not made.exists()  # no session uses it
    # a start that printed an id may have made a session: it is closed
    assert (["reap", "session-x", "--force"] in calls) == (mode == "refuse")


@pytest.mark.parametrize("bad", ["-1", "'600'", "true"])
def test_a_timeout_that_is_no_non_negative_whole_number_is_refused(bad: str) -> None:
    from approvals_harness import loop_md

    with pytest.raises(approvals.Refused, match="cloud_gate_timeout_seconds"):
        approvals.settings(loop_md(f"land:\n  cloud_gate_timeout_seconds: {bad}\n"))


def test_gate_on_takes_host_or_cloud_only() -> None:
    from approvals_harness import loop_md

    with pytest.raises(approvals.Refused, match="gate_on"):
        approvals.settings(loop_md("land:\n  gate_on: both\n"))
    assert approvals.settings(loop_md("land:\n  gate_on: cloud\n")) == {
        "land": {"gate_on": "cloud"}
    }
