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


def test_outside_a_checkout_it_refuses_nothing_and_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A loop.md that sets refuse in a directory no git checkout holds is no policy: the root guard decides."""
    policy(tmp_path, "loop.md", "Settings", "loop:\n  pack_staleness: refuse\n")
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False


@pytest.mark.parametrize(
    "block",
    [
        "loop:\n  pack_staleness: refuse\n",
        'loop:\n  pack_staleness: "refuse"\n',
        "loop:\n  pack_staleness: 'refuse'\n",
        'loop:\n  "pack_staleness": refuse\n',
        "loop:\n  'pack_staleness': 'refuse'   # why\n",
        '"loop":\n  pack_staleness: refuse\n',
        "loop: {pack_staleness: refuse}\n",
        "loop: {cap: 3, pack_staleness: 'refuse'}\n",
        'loop: {cap: 3, "pack_staleness": "refuse"}  # why\n',
    ],
)
def test_every_form_that_sets_refuse_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, block: str
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "loop.md", "Settings", block)
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is True


@pytest.mark.parametrize(
    "block",
    [
        "loop: {\n  pack_staleness: refuse}\n",
        "loop: &a\n  pack_staleness: refuse\n",
        "base: &b\n  pack_staleness: refuse\nloop: *b\n",
    ],
)
def test_a_form_it_cannot_read_is_warn_and_says_so(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    block: str,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "loop.md", "Settings", block)
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False
    assert (
        "form this script cannot read: pack_staleness is treated as warn" in capsys.readouterr().err
    )


def test_a_block_that_never_names_the_key_says_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "loop.md", "Settings", "loop:\n  cap: 3\n")
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False
    assert capsys.readouterr().err == ""


ESCAPED = [
    'loop:\n  pack_staleness: "ref\\x75se"\n',
    'loop:\n  "pack\\x5fstaleness": refuse\n',
    '"l\\x6fop":\n  pack_staleness: refuse\n',
    'loop: {pack_staleness: "ref\\x75se"}\n',
    'loop: {"pack\\x5fstaleness": refuse}\n',
    'loop:\n  cap: 3\n  gate: "a\\tb"\n',
    "loop:\n  pack_staleness: Refuse\n",
    "loop:\n  pack_staleness: refuse now\n",
    'loop:\n  "a b": 3\n',
    "loop:\n  a.b: 3\n",
    'loop:\n  pack_staleness: refuse\n  gate: "a\\tb"\n',
    "loop:\n  <<: *base\n",
]


@pytest.mark.parametrize("block", ESCAPED)
def test_a_form_pyyaml_may_read_differently_is_never_read_silently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    block: str,
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(tmp_path, "loop.md", "Settings", block)
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is False
    assert "cannot read: pack_staleness is treated as warn" in capsys.readouterr().err


def test_a_list_at_the_keys_own_indent_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    policy(
        tmp_path,
        "loop.md",
        "Settings",
        "loop:\n  local_ci_env:\n  - GATE_UI\n  - GATE_X\n  pack_staleness: refuse\n",
    )
    monkeypatch.chdir(tmp_path)
    assert agent.refuses_stale() is True
    assert capsys.readouterr().err == ""
