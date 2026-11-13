"""approvals.py: land finishes the kept --pr worker sessions of each PR it merged (#943)."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from approvals_harness import (
    added,  # noqa: F401
    approvals,
    assigned,  # noqa: F401
    attached,  # noqa: F401
    graphql_answers,  # noqa: F401
    hub,  # noqa: F401
    lands,  # noqa: F401
    others_open,  # noqa: F401
    pushed,  # noqa: F401
    refs,  # noqa: F401
    required,  # noqa: F401
)


def test_a_land_that_merged_the_pr_finishes_its_workers(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    finished: list[int] = []
    monkeypatch.setattr(approvals, "archive_workers", finished.append)
    code, lines = lands["land"]("7")
    assert code == 0, lines
    assert lands["merged"]() == ["7"] and finished == [7]


def test_a_land_that_merged_nothing_finishes_no_worker(
    lands: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    lands["open"](7, {"7.txt": "7\n"})
    finished: list[int] = []
    monkeypatch.setattr(approvals, "archive_workers", finished.append)
    monkeypatch.setattr(approvals, "landable", lambda *_: (approvals.WAITING, True))
    assert lands["land"]("7")[0] == approvals.WAITING
    assert finished == []


def test_archive_workers_runs_reap_merged_for_the_pr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "s1 t: archived (idle)\n", "")

    monkeypatch.setattr(approvals.subprocess, "run", run)
    approvals.archive_workers(7)
    assert calls[0][2:] == ["reap", "--merged", "--pr", "7"]
    assert calls[0][1].endswith("orchestrating-agents/scripts/omnigent_agent.py")
    assert "PR #7: worker sessions: s1 t: archived (idle)" in capsys.readouterr().out


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.CompletedProcess([], 1, "", "no Omnigent login"),
        subprocess.TimeoutExpired([], 120),
        OSError("no python"),
    ],
)
def test_a_failed_archive_is_a_printed_line_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], failure: Any
) -> None:
    def run(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if isinstance(failure, BaseException):
            raise failure
        return failure

    monkeypatch.setattr(approvals.subprocess, "run", run)
    approvals.archive_workers(7)  # raises nothing
    assert "PR #7: worker sessions not finished" in capsys.readouterr().out
