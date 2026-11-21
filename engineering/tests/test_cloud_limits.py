"""cloud_limits.py: a write a cloud session's proxy is known to refuse is skipped in a cloud VM, with no call, one line
naming its stand-in, and the step's own exit code; the table is the one place these limits live (#1637)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "engineering-loop" / "scripts"


def load(name: str) -> object:
    spec = importlib.util.spec_from_file_location(
        f"cloud_limits_test_{name}", SCRIPTS / f"{name}.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


limits = load("cloud_limits")
events = load("events")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, Path]:
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    mine = tmp_path / "a"
    git(tmp_path, "init", "-q", str(mine))
    git(mine, "remote", "add", "origin", str(bare))
    return bare, mine


def test_every_entry_says_cloud_vm_and_formats_with_its_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(limits.CLOUD, "true")
    fields = {"head": "h", "ref": "r", "context": "c", "branch": "b"}
    for write in limits.REFUSED:
        line = limits.skip(write, **fields)
        assert line is not None and line.startswith("cloud VM: ") and "403" not in line


def test_off_the_vm_nothing_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(limits.CLOUD, raising=False)
    assert all(
        limits.skip(write, head="h", ref="r", context="c", branch="b") is None
        for write in limits.REFUSED
    )


def test_a_cloud_event_stays_local_with_one_line_and_no_push(
    clone: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare, mine = clone
    monkeypatch.setenv(limits.CLOUD, "true")
    events.emit("verifier", "loop/7-x", "waiting", cwd=mine)
    assert git(mine, "for-each-ref", "refs/loop/").strip()
    assert not git(bare, "for-each-ref", "refs/loop/").strip()
    err = capsys.readouterr().err
    assert (
        err
        == "cloud VM: events stay local (events.md); refs/loop/verifier/loop/7-x is written here, not pushed\n"
    )


def test_a_host_event_is_still_pushed(
    clone: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    bare, mine = clone
    monkeypatch.delenv(limits.CLOUD, raising=False)
    events.emit("verifier", "loop/7-x", "waiting", cwd=mine)
    assert git(bare, "for-each-ref", "refs/loop/").strip()


def test_a_cloud_clear_leaves_origin_to_the_host(
    clone: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare, mine = clone
    monkeypatch.delenv(limits.CLOUD, raising=False)
    events.emit("verifier", "loop/7-x", "ok", cwd=mine)
    monkeypatch.setenv(limits.CLOUD, "true")
    events.clear("loop/7-x", cwd=mine)
    assert git(bare, "for-each-ref", "refs/loop/").strip()
    assert "origin's refs of loop/7-x are the host's to remove" in capsys.readouterr().err
