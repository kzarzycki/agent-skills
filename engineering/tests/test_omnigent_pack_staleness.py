"""omnigent_agent.py: the same start-up staleness line as approvals.py, and its refusal setting (#942)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "omnigent_agent_stale",
    Path(__file__).resolve().parents[1]
    / "skills"
    / "orchestrating-agents"
    / "scripts"
    / "omnigent_agent.py",
)
assert spec and spec.loader
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

SCRIPT = "scripts/tool.py"


def git(where: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=a@example.com", "-c", "user.name=a", "-C", str(where), *args],
        check=True,
        capture_output=True,
    )


def commit(where: Path, name: str, text: str) -> None:
    (where / name).parent.mkdir(parents=True, exist_ok=True)
    (where / name).write_text(text)
    git(where, "add", "-A")
    git(where, "commit", "-q", "-m", name)


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, Path]:
    origin, work = tmp_path / "origin", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin)], check=True)
    commit(origin, SCRIPT, "v1\n")
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    return origin, work


def test_behind_with_the_script_changed_warns(clone: tuple[Path, Path]) -> None:
    origin, work = clone
    commit(origin, SCRIPT, "v2\n")
    git(work, "fetch", "-q")
    line = agent.pack_behind(work / SCRIPT)
    assert line is not None and "1 commits behind" in line and "git pull" in line


def test_behind_with_the_script_unchanged_is_silent(clone: tuple[Path, Path]) -> None:
    origin, work = clone
    commit(origin, "other.txt", "x\n")
    git(work, "fetch", "-q")
    assert agent.pack_behind(work / SCRIPT) is None


def test_no_upstream_is_silent(tmp_path: Path) -> None:
    alone = tmp_path / "alone"
    subprocess.run(["git", "init", "-q", "-b", "main", str(alone)], check=True)
    commit(alone, SCRIPT, "v1\n")
    assert agent.pack_behind(alone / SCRIPT) is None


def test_refuse_line_in_the_project_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(
        "## Settings\n\n```yaml\nloop:\n  pack_staleness: refuse\n```\n"
    )
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is True
    (tmp_path / "docs" / "agents" / "loop.md").write_text("## Settings\n")
    assert agent.refuses_stale() is False


def test_main_refuses_when_stale_and_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        agent, "pack_behind", lambda _: "omnigent_agent.py: 4 commits behind: run `git pull`"
    )
    monkeypatch.setattr(agent, "refuses_stale", lambda: True)
    assert agent.main(["signature"]) == 1
    assert "git pull" in capsys.readouterr().err
