"""events.py in a cloud session: the event is also a branch the VM can push, and `read` takes either form (#1603)."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "loop_events_cloud",
    Path(__file__).resolve().parent.parent / "skills" / "gatekeeper" / "scripts" / "events.py",
)
events = importlib.util.module_from_spec(spec)
sys.modules["loop_events_cloud"] = events
spec.loader.exec_module(events)

BRANCH = "refs/heads/claude/loop-event/lead/feat/x"


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


def heads(bare: Path, pattern: str) -> list[str]:
    return git(bare, "for-each-ref", "--format=%(refname)", pattern).split()


def test_cloud_emit_also_pushes_the_branch_form(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    bare, a, _ = clones
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    commit = events.emit("lead", "feat/x", "waiting", cwd=a)
    assert git(bare, "rev-parse", BRANCH).strip() == commit
    assert heads(bare, "refs/loop/") == ["refs/loop/lead/feat/x"]


def test_read_picks_up_a_branch_only_event(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    bare, a, b = clones
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    events.emit("lead", "feat/x", "needs-owner", question="Which?\n", cwd=a)
    git(bare, "update-ref", "-d", "refs/loop/lead/feat/x")  # the proxy took only the branch
    (got,) = events.read(cwd=b)
    assert (got["kind"], got["branch"], got["ref"], got["state"], got["question"]) == (
        "lead",
        "feat/x",
        "refs/loop/lead/feat/x",
        "needs-owner",
        "Which?\n",
    )
    assert git(b, "rev-parse", "refs/loop-remote/lead/feat/x").strip() == got["sha"]


def stale_event(clone: Path, state: str, at: str) -> str:
    """A parentless commit holding an event written at `at`, as a producer on another clock would have."""
    data = {"state": state, "seq": 1, "at": at, "beat_s": 300, "url": ""}
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=clone,
        input=json.dumps(data),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "mktree"],
        cwd=clone,
        input=f"100644 blob {blob}\tevent.json\n",
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return subprocess.run(
        ["git", "commit-tree", "-m", "event", tree],
        cwd=clone,
        env={**os.environ, **events.IDENTITY},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_the_newer_event_wins_when_both_forms_exist(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, a, b = clones
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    events.emit("lead", "feat/x", "needs-owner", cwd=a)
    # the branch form is older than the ref form
    git(
        a,
        "push",
        "-q",
        "-f",
        "origin",
        f"{stale_event(a, 'waiting', '2000-01-01T00:00:00Z')}:{BRANCH}",
    )
    (got,) = events.read(cwd=b)
    assert got["state"] == "needs-owner"
    # and now newer
    git(a, "push", "-q", "-f", "origin", f"{stale_event(a, 'ok', '2999-01-01T00:00:00Z')}:{BRANCH}")
    (got,) = events.read(cwd=b)
    assert got["state"] == "ok"


def test_a_host_emit_is_unchanged(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    bare, a, b = clones
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    events.emit("lead", "feat/x", "waiting", cwd=a)
    assert heads(bare, "refs/heads/") == []
    assert heads(bare, "refs/loop/") == ["refs/loop/lead/feat/x"]
    (got,) = events.read(cwd=b)
    assert got["state"] == "waiting"


def test_clear_removes_the_branch_forms(
    clones: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    bare, a, _ = clones
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    events.emit("lead", "feat/x", "ok", cwd=a)
    sha = git(bare, "rev-parse", BRANCH).strip()
    git(bare, "update-ref", "refs/heads/loop-event/lead/feat/x", sha)  # the bare prefix too
    events.clear("feat/x", cwd=a)
    assert heads(bare, "refs/heads/") == []
    assert heads(bare, "refs/loop/") == []
