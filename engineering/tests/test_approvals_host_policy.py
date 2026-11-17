"""approvals.py: a step the host's policy file forbids is refused before it spawns, on every path that runs one."""

from __future__ import annotations

from pathlib import Path

import pytest
from approvals_harness import approvals

POLICY = "# heavy here\nmise run check\napprovals.py local-ci\nswift build\n"


@pytest.fixture
def policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "host-commands"
    path.write_text(POLICY)
    monkeypatch.setenv("AGENT_HOST_COMMANDS", str(path))
    return path


@pytest.mark.parametrize(
    "words",
    [
        ["mise", "run", "check"],
        ["uv", "run", "/x/y/approvals.py", "local-ci", "--run"],
        ["python3", "approvals.py", "local-ci"],
        ["swift", "build", "-c", "release"],
    ],
)
def test_a_listed_command_is_refused(policy: Path, words: list[str]) -> None:
    with pytest.raises(approvals.Refused, match="no gate record.*gate it on an allowed host or in claude-cloud"):
        approvals.run_heavy(words)


def test_the_refusal_spawns_nothing(policy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("spawned")

    monkeypatch.setattr(approvals.subprocess, "Popen", boom)
    with pytest.raises(approvals.Refused):
        approvals.run_heavy(["mise", "run", "check"])
    with pytest.raises(approvals.Refused):
        approvals.heavy(["mise", "run", "check"])


def test_a_command_not_listed_runs(policy: Path) -> None:
    assert approvals.run_heavy(["true"])[0] == 0
    assert approvals.host_forbids(["mise", "run", "test"]) is None


def test_a_host_without_a_policy_runs_everything(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_HOST_COMMANDS", str(tmp_path / "none"))
    assert approvals.host_forbids(["mise", "run", "check"]) is None
    assert approvals.run_heavy(["true"])[0] == 0
