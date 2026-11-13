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
    assert line is not None and "1 commit(s) changed this script" in line and "git pull" in line


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


def test_main_refuses_when_stale_and_set(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        agent, "pack_behind", lambda _: "omnigent_agent.py: 4 commits behind: run `git pull`"
    )
    monkeypatch.setattr(agent, "refuses_stale", lambda: True)
    assert agent.main(["signature"]) == 1
    assert "git pull" in capsys.readouterr().err


def test_a_local_commit_to_the_script_with_upstream_moving_elsewhere_is_silent(
    clone: tuple[Path, Path],
) -> None:
    origin, work = clone
    commit(work, SCRIPT, "local edit\n")
    commit(origin, "other.txt", "x\n")
    git(work, "fetch", "-q")
    assert agent.pack_behind(work / SCRIPT) is None


def test_a_local_commit_to_the_script_with_nothing_new_upstream_is_silent(
    clone: tuple[Path, Path],
) -> None:
    _, work = clone
    commit(work, SCRIPT, "local edit\n")
    assert agent.pack_behind(work / SCRIPT) is None


def test_a_probe_that_fails_says_nothing(
    clone: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, work = clone

    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("no git")

    monkeypatch.setattr(agent.subprocess, "run", broken)
    assert agent.pack_behind(work / SCRIPT) is None


def policy(tmp_path: Path, name: str, heading: str, block: str, prose: str = "") -> None:
    (tmp_path / "docs" / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "agents" / name).write_text(
        f"# Facts\n\n## {heading}\n\n```yaml\n{block}```\n\n{prose}"
    )


EXAMPLE = "An example:\n\n```yaml\nloop:\n  pack_staleness: refuse\n```\n"


@pytest.mark.parametrize(
    ("block", "refuses"),
    [
        ("loop:\n  pack_staleness: refuse\n", True),
        ("loop:\n  cap: 3\n  pack_staleness: refuse   # why\n", True),
        ("loop:\n  pack_staleness: warn\n", False),
        ("loop:\n  cap: 3\n", False),
        ("risk:\n  pack_staleness: refuse\nloop:\n  cap: 3\n", False),
        ("loop:\n  head_proof:\n    pack_staleness: refuse\n", False),
        ("# loop:\n#   pack_staleness: refuse\nloop:\n  cap: 3\n", False),
    ],
)
def test_refuse_is_read_from_the_active_loop_mapping_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, block: str, refuses: bool
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "loop.md", "Settings", block, EXAMPLE)
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is refuses


def test_an_example_elsewhere_in_the_markdown_is_no_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "loop.md", "Settings", "loop:\n  cap: 3\n", EXAMPLE)
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False


def test_gatekeeper_md_is_read_before_loop_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "gatekeeper.md", "Policy", "loop:\n  cap: 3\n")
    policy(tmp_path, "loop.md", "Settings", "loop:\n  pack_staleness: refuse\n")
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False
    policy(tmp_path, "gatekeeper.md", "Policy", "loop:\n  pack_staleness: refuse\n")
    assert agent.refuses_stale() is True


def test_a_loop_md_without_a_settings_block_falls_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text("## Facts\n" + EXAMPLE)
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False
