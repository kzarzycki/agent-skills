"""approvals.py in a cloud session: a failed GitHub read says the verb runs in this session, never a host (#1651)."""

from __future__ import annotations

import subprocess

import pytest
from approvals_harness import approvals


def failing_gh(*_a: object, **_k: object) -> None:
    raise subprocess.CalledProcessError(
        1, ["gh", "api", "repos/o/r/pulls/7"], stderr="HTTP 401: Bad credentials"
    )


@pytest.mark.parametrize("argv", [["local-ci", "7"], ["check", "merge", "7"], ["land", "7"]])
def test_a_failed_github_read_in_a_cloud_session_names_the_rest_route(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(approvals, "dispatch", failing_gh)
    assert approvals.main(argv) == 1
    out = capsys.readouterr().out
    assert "HTTP 401: Bad credentials" in out
    assert "reads GitHub here through REST wherever GraphQL answers 403" in out
    assert "run this same command again in this session" in out
    assert "never start a host or child session for it" in out


def test_on_a_host_or_for_another_command_the_failure_is_printed_alone(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setattr(approvals, "dispatch", failing_gh)
    assert approvals.main(["local-ci", "7"]) == 1
    assert capsys.readouterr().out.strip() == "HTTP 401: Bad credentials"
    git = subprocess.CalledProcessError(1, ["git", "fetch"], stderr="x")
    assert approvals.cloud_read_note(git, {"CLAUDE_CODE_REMOTE": "true"}) == ""
