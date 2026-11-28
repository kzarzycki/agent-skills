"""approvals.py write-pending: the host writes the `gate` status and the verifier event a cloud session's proxy
refuses it (#3053), from what origin proves, and never runs the gate."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import (
    HEAD,
    LOOP,
    TREE,
    approvals,
    github,  # noqa: F401
)


@pytest.fixture
def open_pr(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """One open PR at HEAD, in a project of the plain gate; the list holds each command the test's process ran."""
    ran: list[str] = []
    monkeypatch.setattr(
        approvals,
        "open_pulls",
        lambda: [{"number": 7, "headRefName": "feat/x", "baseRefName": "main"}],
    )
    monkeypatch.setattr(
        approvals, "pull_status", lambda _n: {"headRefOid": HEAD, "baseRefName": "main"}
    )
    monkeypatch.setattr(approvals, "tree_of", lambda _head: TREE)
    monkeypatch.setattr(approvals, "project", lambda **_k: (None, LOOP))
    monkeypatch.setattr(approvals, "pending_events", lambda _branch: 0)
    monkeypatch.setattr(approvals, "run_local_ci", lambda *a, **k: ran.append("gate") or {})
    monkeypatch.setattr(approvals, "run_heavy", lambda *a, **k: ran.append("gate") or 0)
    return ran


def gate_statuses(hub: dict[str, list[dict[str, Any]]]) -> list[str]:
    return [s["description"] for s in hub.get(HEAD, []) if s["context"] == "gate"]


def origin_pass(refs: dict[str, dict[str, Any]]) -> None:
    """What a cloud session's `local-ci --record` leaves on origin: the record branch, and no status."""
    command = approvals.gate()[0]
    approvals.push_record(
        {"tree": TREE, "head": HEAD, "command": command, "time": "2026-10-01T09:00:00Z", "exit": 0}
    )
    assert refs


def test_a_head_with_a_record_on_origin_gets_its_gate_status_and_no_gate_runs(
    open_pr: list[str],
    hub: dict[str, list[dict[str, Any]]],
    refs: dict[str, dict[str, Any]],
) -> None:
    origin_pass(refs)
    assert approvals.main(["write-pending"]) == 0
    assert gate_statuses(hub) == [approvals.described(TREE, HEAD, approvals.gate()[0])]
    assert open_pr == []


def test_a_head_with_no_pass_record_gets_no_status(
    open_pr: list[str],
    hub: dict[str, list[dict[str, Any]]],
    refs: dict[str, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert approvals.main(["write-pending"]) == 0
    assert gate_statuses(hub) == []
    assert "origin holds no pass" in capsys.readouterr().out


def test_run_twice_it_writes_nothing_the_second_time(
    open_pr: list[str],
    hub: dict[str, list[dict[str, Any]]],
    refs: dict[str, dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    origin_pass(refs)
    approvals.main(["write-pending"])
    capsys.readouterr()
    assert approvals.main(["write-pending"]) == 0
    assert len(gate_statuses(hub)) == 1
    assert "wrote the `gate` status" not in capsys.readouterr().out


def test_a_refused_write_is_said_once_and_not_retried(
    open_pr: list[str],
    refs: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []

    def refuse(*_a: Any, **_k: Any) -> None:
        calls.append("post")
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403")

    monkeypatch.setattr(approvals, "statuses", lambda _head: [])
    monkeypatch.setattr(approvals, "post_status", refuse)
    origin_pass(refs)
    assert approvals.main(["write-pending"]) == 0
    assert calls == ["post"]
    assert "was not written: HTTP 403" in capsys.readouterr().out


def test_a_refused_record_run_names_the_host_command(
    open_pr: list[str],
    refs: dict[str, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refuse(*_a: Any, **_k: Any) -> None:
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403")

    monkeypatch.setattr(approvals, "post_status", refuse)
    origin_pass(refs)
    record = refs[approvals.record_name(TREE, approvals.gate()[0])]
    approvals.publish(HEAD, {**record, "published": True})
    out = capsys.readouterr().out
    assert "write-pending" in out
    assert "the record is on origin" in out


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def test_a_cloud_verifiers_event_branch_reaches_its_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bare, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(tmp_path, "init", "-q", str(clone))
    git(clone, "remote", "add", "origin", str(bare))
    # a cloud VM's emit: the ref is refused, so only the branch form is on origin
    commit = approvals.loop_events.emit("verifier", "feat/x", "ok", cwd=clone)
    git(clone, "push", "-q", "origin", f"{commit}:refs/heads/loop-event/verifier/feat/x")
    git(clone, "push", "-q", "origin", "--delete", "refs/loop/verifier/feat/x")
    monkeypatch.chdir(clone)
    assert approvals.pending_events("feat/x") == 1
    assert git(bare, "rev-parse", "refs/loop/verifier/feat/x").strip() == commit
    assert approvals.pending_events("feat/x") == 0
