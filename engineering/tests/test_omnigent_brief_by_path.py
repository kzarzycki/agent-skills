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
    assert err.count("\n") == 1 and "over 8000" in err and "inlined role file" in err
    git(repo, "add", "big.md")
    git(repo, "commit", "-qm", "big")
    code, out, err = brief(capsys, "--role", "big.md")
    assert code == 0 and len(out) < CAP and "bytes" not in out


def test_an_in_cap_message_reports_its_length_on_stderr(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = brief(capsys, "--role", "role.md")
    assert code == 0 and err == f"brief: {len(out)} characters\n"


def sized(capsys: pytest.CaptureFixture[str], size: int, *args: str) -> tuple[int, str, str]:
    """``brief`` whose whole message is ``size`` characters, by padding an inline task."""
    omnigent_agent.main(["brief", "do it", "r.md", *args])
    base = len(capsys.readouterr().out) - len("do it")
    code = omnigent_agent.main(["brief", "x" * (size - base), "r.md", *args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_the_cap_is_inclusive_at_8000_and_cloud_only(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert sized(capsys, CAP, "--cloud")[0] == 0
    assert sized(capsys, CAP + 1, "--cloud")[0] == 2
    code, out, _ = sized(capsys, CAP + 500)  # a host child's message has no such cap
    assert code == 0 and len(out) == CAP + 500


def test_an_over_cap_by_path_role_is_not_blamed_on_the_role_file(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = sized(capsys, CAP + 100, "--cloud", "--role", "role.md")
    assert code == 2 and out == "" and err.count("\n") == 1
    assert "longest part is the brief" in err


def test_a_committed_file_of_another_checkout_is_inlined(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path_factory.mktemp("other")
    git(other, "init", "-q")
    (other / "ext.md").write_text("FOREIGN TEXT")
    git(other, "add", "ext.md")
    git(other, "commit", "-qm", "ext")
    assert "FOREIGN TEXT" in brief(capsys, "--role", str(other / "ext.md"))[1]
    code = omnigent_agent.main(["brief", str(other / "ext.md"), "r.md", "--cloud"])
    assert code == 0 and "FOREIGN TEXT" in capsys.readouterr().out


def test_a_file_named_like_a_pathspec_is_matched_literally(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "task1.md").write_text("TRACKED")
    git(repo, "add", "task1.md")
    git(repo, "commit", "-qm", "t")
    (repo / "task[1].md").write_text("BRACKET TEXT")
    assert "BRACKET TEXT" in brief(capsys, "--role", "task[1].md")[1]
    omnigent_agent.main(["brief", "task[1].md", "r.md", "--cloud"])
    assert "BRACKET TEXT" in capsys.readouterr().out


def test_an_edit_hidden_by_assume_unchanged_is_still_inlined(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo, "update-index", "--assume-unchanged", "role.md")
    (repo / "role.md").write_text("HIDDEN EDIT")
    assert "HIDDEN EDIT" in brief(capsys, "--role", "role.md")[1]


def test_a_cloud_start_judges_the_role_against_the_workspace_it_names(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_omnigent_agent import CloudFake

    workspace = tmp_path_factory.mktemp("workspace")
    git(workspace, "init", "-q")
    git(workspace, "commit", "-qm", "empty", "--allow-empty")
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    cloud = CloudFake()
    sid, _ = omnigent_agent.start(
        cloud, "claude-cloud", "t", "do X", repo / "r.md", "role.md", 0, workspace=str(workspace)
    )
    text = omnigent_agent.text_of(cloud.sessions[sid][1])
    assert "ROLE BODY" in text and "in your checkout" not in text


def test_the_role_help_says_a_tracked_file_goes_by_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        omnigent_agent.main(["brief", "--help"])
    assert "repo path" in " ".join(capsys.readouterr().out.split())
