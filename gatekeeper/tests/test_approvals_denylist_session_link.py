"""The deny list lets an Omnigent session link through and still refuses its term anywhere else (#2571)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_approvals import approvals

LINK = "https://build-host.local:8443/c/" + "0123456789abcdef" * 2


@pytest.fixture
def deny(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    listed = tmp_path / "deny.txt"
    listed.write_text("# hosts\nbuild-host.local\n")
    monkeypatch.setenv("LOOP_DENY_LIST", str(listed))
    return listed


def test_a_listed_host_inside_a_session_link_is_accepted(
    deny: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        approvals.subprocess,
        "run",
        lambda command, **_kw: calls.append(command) or subprocess.CompletedProcess(command, 0, ""),
    )
    approvals.comment(7, f"Session: {LINK}\nand http://BUILD-host.local/c/{'ab' * 16} again.\n")
    assert calls


@pytest.mark.parametrize(
    "body, line",
    [
        ("Ran on build-host.local\n", 1),
        (f"Session: {LINK}\nbut also build-host.local here\n", 2),
        (f"{LINK} and {LINK.replace('/c/', '/x/')}\n", 1),  # not a session link: no /c/<id>
        (f"{LINK}/../build-host.local\n", 1),
        ("https://build-host.local:8443/c/abc123\n", 1),  # a short id is no session link
    ],
)
def test_the_same_host_outside_a_session_link_is_refused(
    deny: Path, monkeypatch: pytest.MonkeyPatch, body: str, line: int
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        approvals.subprocess,
        "run",
        lambda command, **_kw: calls.append(command) or subprocess.CompletedProcess(command, 0, ""),
    )
    with pytest.raises(approvals.Refused) as refused:
        approvals.comment(7, body)
    assert str(refused.value) == (
        f"refused to post: line {line} names `build-host.local` from the deny list (LOOP_DENY_LIST); nothing posted"
    )
    assert calls == []
