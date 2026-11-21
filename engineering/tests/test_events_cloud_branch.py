"""events.py in a cloud session: the event is also pushed as a branch the VM's proxy lets through (#1603)."""

from __future__ import annotations

import importlib.util
import stat
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "loop_events_cloud_branch",
    Path(__file__).resolve().parent.parent
    / "skills"
    / "engineering-loop"
    / "scripts"
    / "events.py",
)
events = importlib.util.module_from_spec(spec)
sys.modules["loop_events_cloud_branch"] = events
spec.loader.exec_module(events)

BRANCH = "refs/heads/loop-event/lead/feat/x"
LOOP = "refs/loop/lead/feat/x"
MIRROR = "refs/loop-remote/lead/feat/x"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def proxy(bare: Path) -> None:
    """Make `bare` refuse a push outside refs/heads/, as a cloud session's git proxy does (HTTP 403)."""
    hook = bare / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\nwhile read old new ref; do case $ref in refs/heads/*) ;; *) exit 1;; esac; done\n"
    )
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)


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


@pytest.fixture
def cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)


def origin_refs(bare: Path) -> list[str]:
    return git(bare, "for-each-ref", "--format=%(refname)").split()


def test_cloud_emit_pushes_the_branch_form(clones, cloud) -> None:
    bare, a, _ = clones
    proxy(bare)
    commit = events.emit("lead", "feat/x", "waiting", cwd=a)
    assert origin_refs(bare) == [BRANCH]
    assert git(bare, "rev-parse", BRANCH).strip() == commit
    # a beat rewrites the branch with a new parentless commit
    again = events.emit("lead", "feat/x", "needs-owner", question="Which?\n", cwd=a)
    assert git(bare, "rev-parse", BRANCH).strip() == again
    assert git(bare, "rev-list", "--count", BRANCH).strip() == "1"


def test_cloud_emit_with_origin_unreachable_still_returns(
    clones, cloud, capsys: pytest.CaptureFixture[str]
) -> None:
    bare, a, _ = clones
    git(a, "remote", "set-url", "origin", str(bare.parent / "missing.git"))
    commit = events.emit("lead", "feat/x", "waiting", cwd=a)
    assert git(a, "rev-parse", LOOP).strip() == commit
    assert "not pushed" in capsys.readouterr().err


def test_read_picks_up_a_branch_only_event(clones, cloud) -> None:
    bare, a, b = clones
    proxy(bare)
    events.emit(
        "lead", "feat/x", "needs-owner", url="https://example.test/1", question="Q?\n", cwd=a
    )
    (got,) = events.read(cwd=b)
    assert (got["kind"], got["branch"], got["ref"], got["state"]) == (
        "lead",
        "feat/x",
        LOOP,
        "needs-owner",
    )
    assert (got["url"], got["question"]) == ("https://example.test/1", "Q?\n")
    assert git(b, "rev-parse", MIRROR).strip() == got["sha"]
    assert [e["ref"] for e in events.read("lead", cwd=b)] == [LOOP]
    assert events.read("land", cwd=b) == []


def test_newer_event_wins_when_both_forms_exist(clones, monkeypatch: pytest.MonkeyPatch) -> None:
    bare, a, b = clones
    stamps = iter(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"])
    monkeypatch.setattr(events, "now", lambda: next(stamps))
    # the host's ref is older, the cloud's branch newer
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    events.emit("lead", "feat/x", "waiting", cwd=a)
    proxy(bare)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    events.emit("lead", "feat/x", "ok", cwd=b)
    assert sorted(origin_refs(bare)) == sorted([LOOP, BRANCH])
    (got,) = events.read(cwd=b)
    assert got["state"] == "ok"
    assert git(b, "rev-parse", MIRROR).strip() == got["sha"]


def test_the_ref_wins_when_it_is_the_newer(clones, monkeypatch: pytest.MonkeyPatch) -> None:
    bare, a, b = clones
    stamps = iter(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"])
    monkeypatch.setattr(events, "now", lambda: next(stamps))
    proxy(bare)
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    events.emit("lead", "feat/x", "waiting", cwd=b)
    # the bare takes a ref outside refs/heads/ again: a host wrote it later
    (bare / "hooks" / "pre-receive").unlink()
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    events.emit("lead", "feat/x", "failed", cwd=a)
    (got,) = events.read(cwd=b)
    assert got["state"] == "failed"
    assert git(b, "rev-parse", MIRROR).strip() == got["sha"]


def test_host_emit_is_unchanged(clones, host) -> None:
    bare, a, b = clones
    events.emit("lead", "feat/x", "waiting", cwd=a)
    assert origin_refs(bare) == [LOOP]
    (got,) = events.read(cwd=b)
    assert (got["state"], got["ref"]) == ("waiting", LOOP)


def test_clear_removes_the_branch_form(clones, cloud) -> None:
    bare, a, _ = clones
    events.emit("lead", "feat/x", "waiting", cwd=a)
    events.emit("land", "feat/x", "waiting", cwd=a)
    events.emit("lead", "feat/y", "waiting", cwd=a)
    events.clear("feat/x", cwd=a)
    assert origin_refs(bare) == ["refs/heads/loop-event/lead/feat/y", "refs/loop/lead/feat/y"]


def test_wait_sees_a_branch_only_event(clones, cloud) -> None:
    bare, a, b = clones
    proxy(bare)
    events.emit("lead", "feat/x", "ok", url="https://example.test/9", cwd=a)
    import io

    out = io.StringIO()
    assert events.wait("lead", "feat/x", timeout=5, poll=0.1, cwd=b, out=out) == 0
    assert "https://example.test/9" in out.getvalue()
