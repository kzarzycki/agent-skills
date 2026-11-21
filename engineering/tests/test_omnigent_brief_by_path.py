"""omnigent_agent.py: ``brief --cloud`` names a tracked, unchanged file by repo path (#1604)."""

import subprocess
from pathlib import Path

import pytest
from test_omnigent_agent import omnigent_agent

CAP = 8000


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "role.md").write_text("ROLE BODY " * 20)
    git(tmp_path, "add", "role.md")
    git(tmp_path, "commit", "-qm", "role")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def brief(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = omnigent_agent.main(["brief", "do it", "r.md", "--cloud", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_a_tracked_role_file_is_named_by_its_repo_path(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = brief(capsys, "--role", str(repo / "role.md"))
    assert code == 0
    assert "Your role file is `role.md` in your checkout: read it first and follow it" in out
    assert "ROLE BODY" not in out


def test_an_untracked_or_modified_role_file_is_inlined(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "new.md").write_text("NEW ROLE")
    assert "NEW ROLE" in brief(capsys, "--role", "new.md")[1]
    (repo / "role.md").write_text("EDITED ROLE")
    code, out, _ = brief(capsys, "--role", "role.md")
    assert (code, "EDITED ROLE" in out, "in your checkout" in out) == (0, True, False)


def test_a_role_file_outside_the_repo_is_inlined(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path_factory.mktemp("elsewhere") / "role.md"
    other.write_text("OUTSIDE ROLE")
    assert "OUTSIDE ROLE" in brief(capsys, "--role", str(other))[1]


def test_a_brief_file_follows_the_same_rule(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "loose.md").write_text("LOOSE TASK")
    code = omnigent_agent.main(["brief", "loose.md", "r.md", "--cloud"])
    assert "LOOSE TASK" in capsys.readouterr().out and code == 0
    code = omnigent_agent.main(["brief", "role.md", "r.md", "--cloud"])
    out = capsys.readouterr().out
    assert "`role.md` in your checkout" in out and "ROLE BODY" not in out


def test_an_over_cap_message_exits_2_naming_the_cause_and_prints_nothing_on_stdout(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "big.md").write_text("x" * (CAP + 1))
    code, out, err = brief(capsys, "--role", "big.md")
    assert code == 2 and out == ""
    assert "big.md" not in out and "over 8000" in err and "role file" in err
    git(repo, "add", "big.md")
    git(repo, "commit", "-qm", "big")
    code, out, err = brief(capsys, "--role", "big.md")
    assert code == 0 and len(out) < CAP and "bytes" not in out


def test_an_in_cap_message_reports_its_length_on_stderr(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = brief(capsys, "--role", "role.md")
    assert code == 0 and f"{len(out)} characters" in err
