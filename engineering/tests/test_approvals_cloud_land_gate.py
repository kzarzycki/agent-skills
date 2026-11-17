"""approvals.py: `land: gate_on: cloud` gates the batch tree in a cloud session, the host as the fallback (#1033)."""

from __future__ import annotations

import json
import time as real_time
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    GITHUB_RULE,
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    board_risks,  # noqa: F401
    git_in,
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)

TIMEOUT = 100


class Clock:
    """A stubbed `time` for approvals: `sleep` moves `monotonic` by what it is asked, then runs `tick(now)`."""

    def __init__(self) -> None:
        self.now, self.slept, self.tick = 0.0, [], lambda _now: None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert sum(self.slept) < 10_000, "the wait never ends"
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
    kept = json.loads((session["repo"] / ".git" / "approvals" / "cloud-gate.json").read_text())
    assert kept == {"session": "session-2"}


def test_a_session_that_is_gone_is_replaced(session: dict[str, Any]) -> None:
    assert approvals.ask_cloud_gate("t1") == ""
    session["mode"]("gone")
    assert approvals.ask_cloud_gate("t2") == ""
    assert [call[0] for call in session["calls"]()] == [
        "launch-dir",
        "start",
        "relay",
        "launch-dir",
        "start",
    ]


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
