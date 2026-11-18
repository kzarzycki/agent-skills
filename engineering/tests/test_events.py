"""events.py: a step's state as a git ref, written in one clone and read in another through a bare remote (#1375)."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "loop_events",
    Path(__file__).resolve().parent.parent
    / "skills"
    / "engineering-loop"
    / "scripts"
    / "events.py",
)
events = importlib.util.module_from_spec(spec)
sys.modules["loop_events"] = events
spec.loader.exec_module(events)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def clones(tmp_path: Path) -> tuple[Path, Path, Path]:
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    made = []
    for name in ("a", "b"):
        clone = tmp_path / name
        git(tmp_path, "init", "-q", str(clone))
        git(clone, "remote", "add", "origin", str(bare))
        made.append(clone)
    return bare, made[0], made[1]


def test_event_round_trips_between_clones(clones: tuple[Path, Path, Path]) -> None:
    _, a, b = clones
    events.emit(
        "lead",
        "feat/x",
        "needs-owner",
        url="https://example.test/1",
        question="Which one?\n\nA or B.\n",
        cwd=a,
    )
    (got,) = events.read("lead", cwd=b)
    assert (got["state"], got["url"], got["question"], got["branch"], got["kind"]) == (
        "needs-owner",
        "https://example.test/1",
        "Which one?\n\nA or B.\n",
        "feat/x",
        "lead",
    )
    assert got["seq"] == 1 and got["beat_s"] == events.BEATS["lead"]


def test_read_fetches_only_a_moved_sha(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, a, b = clones
    events.emit("land", "x", "waiting", cwd=a)
    first = events.read(cwd=b)[0]
    fetched = []
    real = events.fetch_event
    monkeypatch.setattr(
        events, "fetch_event", lambda cwd, ref: fetched.append(ref) or real(cwd, ref)
    )
    again = events.read(cwd=b)[0]
    assert fetched == [] and again["changed"] == first["changed"]
    time.sleep(1.1)
    events.emit("land", "x", "waiting", cwd=a)
    moved = events.read(cwd=b)[0]
    assert fetched == [moved["ref"]] and moved["seq"] == 2 and moved["changed"] > first["changed"]


def test_beat_leaves_no_history(clones: tuple[Path, Path, Path]) -> None:
    bare, a, _ = clones
    events.emit("gate", "x", "waiting", cwd=a)
    events.emit("gate", "x", "waiting", cwd=a)
    ref = "refs/loop/gate/x"
    assert git(a, "rev-list", "--count", ref).strip() == "1"
    assert git(bare, "rev-list", "--count", ref).strip() == "1"
    assert git(a, "rev-parse", ref) == git(bare, "rev-parse", ref)


def test_wait_exit_codes(clones: tuple[Path, Path, Path]) -> None:
    _, a, b = clones
    out = []
    sink = type("S", (), {"write": lambda self, s: out.append(s), "flush": lambda self: None})()
    # another process emits ok while this one waits (from the other clone, through the remote)
    events.emit("land", "x", "waiting", cwd=a)
    threading.Timer(
        0.5, lambda: events.emit("land", "x", "ok", url="https://example.test/p", cwd=a)
    ).start()
    assert events.wait("land", "x", poll=0.1, timeout=10, cwd=b, out=sink) == 0
    events.emit("land", "y", "failed", cwd=a)
    assert events.wait("land", "y", poll=0.1, timeout=5, cwd=b, out=sink) == 1
    events.emit("lead", "y", "needs-owner", question="Go?\n", cwd=a)
    assert events.wait("lead", "y", poll=0.1, timeout=5, cwd=b, out=sink) == 2
    assert "Go?" in "".join(out)
    # a waiting ref nobody rewrites is silent past twice its beat; one still beating is not
    events.emit("gate", "z", "waiting", beat=0.3, cwd=a)
    assert events.wait("gate", "z", poll=0.1, timeout=10, cwd=b, out=sink) == 4
    events.emit("gate", "q", "waiting", beat=60, cwd=a)
    assert events.wait("gate", "q", poll=0.1, timeout=0.5, cwd=b, out=sink) == 3
    # nothing there at all is unknown, not an end
    assert events.wait("gate", "none", poll=0.1, timeout=0.3, cwd=b, out=sink) == 3


def test_unreadable_event_is_unknown_not_ended(clones: tuple[Path, Path, Path]) -> None:
    _, a, _ = clones
    tree = subprocess.run(
        ["git", "mktree"], cwd=a, input="", text=True, capture_output=True, check=True
    ).stdout.strip()
    commit = git(
        a, "-c", "user.name=t", "-c", "user.email=t@t", "commit-tree", "-m", "junk", tree
    ).strip()
    git(a, "update-ref", "refs/loop/lead/j", commit)
    assert events.event_at(a, commit)["state"] == "unknown"
    assert events.wait("lead", "j", poll=0.1, timeout=0.3, cwd=a, out=io.StringIO()) == 3


def test_emit_offline_is_not_a_failure(
    clones: tuple[Path, Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, a, _ = clones
    git(a, "remote", "set-url", "origin", str(tmp_path / "nowhere.git"))
    assert events.main(["--repo", str(a), "emit", "lead", "x", "waiting"]) == 0
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and err[0].startswith("events: refs/loop/lead/x written here, not pushed")
    local = json.loads(git(a, "show", "refs/loop/lead/x:event.json"))
    assert local["state"] == "waiting"
    # a native lead in the same clone still waits on it
    events.emit("lead", "x", "ok", cwd=a)
    assert events.wait("lead", "x", poll=0.1, timeout=2, cwd=a, out=io.StringIO()) == 0


def test_clear_removes_refs_here_and_on_origin(clones: tuple[Path, Path, Path]) -> None:
    bare, a, b = clones
    events.emit("lead", "x", "waiting", cwd=a)
    events.emit("land", "x", "waiting", cwd=a)
    events.emit("land", "keep", "waiting", cwd=a)
    events.read(cwd=b)
    events.clear("x", cwd=a)
    events.clear("x", cwd=b)
    assert git(bare, "for-each-ref", "--format=%(refname)", "refs/loop/").split() == [
        "refs/loop/land/keep"
    ]
    assert git(a, "for-each-ref", "--format=%(refname)", "refs/loop/").split() == [
        "refs/loop/land/keep"
    ]
    assert git(b, "for-each-ref", "--format=%(refname)", "refs/loop-remote/").split() == [
        "refs/loop-remote/land/keep"
    ]


def test_cli_emit_read_round_trip(clones: tuple[Path, Path, Path], tmp_path: Path) -> None:
    _, a, b = clones
    question = tmp_path / "q.md"
    question.write_text("Go?\n")
    script = Path(events.__file__)

    def run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), "--repo", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
        )

    assert (
        run(
            a,
            "emit",
            "lead",
            "b1",
            "needs-owner",
            "--url",
            "https://example.test/9",
            "--question",
            str(question),
        ).returncode
        == 0
    )
    read = run(b, "read", "--json")
    assert read.returncode == 0 and json.loads(read.stdout)["question"] == "Go?\n"
    assert run(b, "wait", "lead", "b1", "--timeout", "2").returncode == 2
