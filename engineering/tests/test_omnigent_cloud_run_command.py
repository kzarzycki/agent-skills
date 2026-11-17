"""`cloud-run` runs one command in a cloud session on the checkout's HEAD and exits with its
code, and a child placed on a host is told the host-run prefix (#1233)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    CloudFake,
    FakeOmnigent,
    no_model,
    no_sleep,
    omnigent_agent,
    this_repo,
    trusted_folders,
)
from test_omnigent_launch_dir import bare, checkout, git  # noqa: F401  (a fixture by name)

FAILED = omnigent_agent.CLOUD_RUN_FAILED
RESULT = "REPORT\nEXIT: 3\n2 failed, 40 passed\nFAILED tests/test_a.py::test_x - assert 1 == 2\n"


@pytest.fixture
def repo(tmp_path: Path, bare: Path, monkeypatch: pytest.MonkeyPatch) -> Path:  # noqa: F811
    """A checkout of ``bare`` on ``main``, tracking origin, with the environment resolved."""
    monkeypatch.setattr(
        omnigent_agent, "resolve_environment", lambda env, repo: ("env_1", "agent-skills")
    )
    return checkout(bare, tmp_path / "main")


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every nested ``run`` argv cloud-run makes, passed on to the real one."""
    made: list[list[str]] = []
    real = omnigent_agent.command_of

    def recording(argv: list[str]) -> int:
        made.append(argv)
        return real(argv)

    monkeypatch.setattr(omnigent_agent, "command_of", recording)
    return made


def serve(monkeypatch: pytest.MonkeyPatch, og: FakeOmnigent) -> FakeOmnigent:
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    return og


def cloud_run(repo: Path, *command: str) -> int:
    return omnigent_agent.main(["cloud-run", "--checkout", str(repo), "--", *command])


def test_cloud_run_refuses_tracked_changes_before_any_session_exists(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = serve(monkeypatch, CloudFake(reply=RESULT))
    (repo / "a.txt").write_text("changed")
    assert cloud_run(repo, "pytest -q") == FAILED
    err = capsys.readouterr().err
    assert "tracked changes (a.txt)" in err and "`git push`" in err
    assert "LOOP_HOST_RUN=<why the cloud route failed> pytest -q" in err
    assert not og.sessions and not (repo / ".worktrees").exists()


def test_cloud_run_refuses_a_head_its_remote_lacks_before_any_session_exists(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = serve(monkeypatch, CloudFake(reply=RESULT))
    (repo / "c.txt").write_text("c")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "unpushed", cwd=repo)
    assert cloud_run(repo, "pytest -q") == FAILED
    err = capsys.readouterr().err
    assert "is not on origin/main" in err and "`git push -u origin main`" in err
    assert not og.sessions and not (repo / ".worktrees").exists()


def test_cloud_run_refuses_a_detached_head(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = serve(monkeypatch, CloudFake(reply=RESULT))
    git("checkout", "-q", "--detach", "HEAD", cwd=repo)
    assert cloud_run(repo, "pytest") == FAILED
    assert "detached HEAD" in capsys.readouterr().err and not og.sessions


def test_cloud_run_exits_with_the_command_s_code_and_prints_the_report_path(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    runs: list[list[str]],
) -> None:
    og = serve(monkeypatch, CloudFake(reply=RESULT))
    assert cloud_run(repo, "pytest -q") == 3
    out = capsys.readouterr().out
    launch = repo / ".worktrees" / "cloud-run-main"
    report = Path(out.strip())
    assert out.count("\n") == 1 and report.parent == launch / "tmp" / "loop"
    assert "EXIT: 3" in report.read_text() and "test_a.py::test_x" in report.read_text()
    (argv,) = runs
    assert argv[:2] == ["run", "claude-cloud"]
    assert argv[argv.index("--workspace") + 1] == str(launch)
    assert "--no-keep" in argv
    assert argv[argv.index("--model") + 1] == "haiku" == omnigent_agent.CLOUD_RUN_MODEL
    assert argv[argv.index("--permission-mode") + 1] == "auto"
    (sid,) = og.sessions
    assert og.overrides[sid] == "haiku" and sid in og.archived  # --no-keep: finished
    head = git("rev-parse", "HEAD", cwd=repo)
    brief = omnigent_agent.text_of(og.sessions[sid][1])
    assert f"git checkout --detach {head}" in brief and "```sh\npytest -q\n```" in brief
    assert "`EXIT: <n>`" in brief and "every failure" in brief
    assert git("rev-parse", "HEAD", cwd=launch) == head


def test_cloud_run_returns_zero_for_a_green_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    serve(monkeypatch, CloudFake(reply="REPORT\nEXIT: 0\n42 passed\n"))
    assert cloud_run(repo, "uv", "run", "pytest", "-k", "a or b") == 0


def test_cloud_run_reuses_the_launch_dir_and_points_it_at_the_branch(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    runs: list[list[str]],
) -> None:
    serve(monkeypatch, CloudFake(reply=RESULT))
    made: list[Path] = []
    real = omnigent_agent.launch_dir
    monkeypatch.setattr(
        omnigent_agent,
        "launch_dir",
        lambda remote, branch, env, path, **kw: (
            made.append(path) or real(remote, branch, env, path, **kw)
        ),
    )
    assert cloud_run(repo, "pytest") == 3
    (repo / "c.txt").write_text("c")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "next", cwd=repo)
    git("push", "-q", "origin", "main", cwd=repo)
    assert cloud_run(repo, "pytest") == 3
    launch = repo / ".worktrees" / "cloud-run-main"
    assert made == [launch]  # made once, then reused
    assert [a[a.index("--workspace") + 1] for a in runs] == [str(launch)] * 2
    assert git("rev-parse", "HEAD", cwd=launch) == git("rev-parse", "HEAD", cwd=repo)
    assert git("symbolic-ref", "--short", "HEAD", cwd=repo) == "main"  # the checkout untouched
    # the commit's `git add .` left the launch dir out, though the repo ignores no .worktrees/
    assert (
        git("ls-files", ".worktrees", cwd=repo) == ""
        and git("status", "--porcelain", cwd=repo) == ""
    )


@pytest.mark.parametrize(
    "og",
    [
        CloudFake(reply="REPORT\n2 failed, 40 passed\n"),  # no EXIT line
        CloudFake(reply="REPORT\nEXIT: none\nuv is missing\n"),  # the command never ran
        CloudFake(reply=RESULT, status="failed"),  # the session failed
    ],
)
def test_a_failed_cloud_route_exits_with_its_own_code_and_prints_the_fallback(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    og: FakeOmnigent,
) -> None:
    serve(monkeypatch, og)
    assert cloud_run(repo, "pytest -q") == FAILED == 125
    err = capsys.readouterr().err
    assert "cloud-run: " in err
    assert f"cd {repo} && LOOP_HOST_RUN=<why the cloud route failed> pytest -q" in err


def test_a_failed_launch_exits_with_its_own_code_and_prints_the_fallback(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = CloudFake(reply=RESULT)
    og.fail = {"send"}
    serve(monkeypatch, og)
    assert cloud_run(repo, "make test") == FAILED
    err = capsys.readouterr().err
    assert "cloud-run: the cloud run ended with exit 1" in err
    assert "LOOP_HOST_RUN=<why the cloud route failed> make test" in err


def test_cloud_run_needs_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert omnigent_agent.main(["cloud-run", "--"]) == 2
    assert "cloud-run needs -- COMMAND" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("words", "text"),
    [
        (["pytest -q && ruff check"], "pytest -q && ruff check"),
        (["pytest", "-k", "a or b"], "pytest -k 'a or b'"),
    ],
)
def test_one_argument_is_shell_text_and_several_are_words(words: list[str], text: str) -> None:
    assert omnigent_agent.shell_text(words) == text


def test_a_host_child_s_preamble_has_the_host_run_line(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    omnigent_agent.start(FakeOmnigent(), "claude", "t", "do X", report, None, 0)
    brief = omnigent_agent.brief_of(report).read_text()
    assert omnigent_agent.HOST_RUN_LINE in brief and "`LOOP_HOST_RUN=placed `" in brief


@pytest.mark.parametrize(("top_level", "pr"), [(False, None), (True, None), (False, 7)])
def test_a_cloud_child_s_preamble_has_no_host_run_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, top_level: bool, pr: int | None
) -> None:
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    og = CloudFake()
    sid, _ = omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, top_level=top_level, pr=pr
    )
    assert "LOOP_HOST_RUN" not in omnigent_agent.text_of(og.sessions[sid][1])


def test_a_host_lead_s_preamble_has_no_host_run_line(tmp_path: Path) -> None:
    """A lead's own heavy runs are the ones the hook sends to the cloud."""
    report = tmp_path / "r.md"
    omnigent_agent.start(FakeOmnigent(), "claude", "t", "do X", report, None, 0, top_level=True)
    assert "LOOP_HOST_RUN" not in omnigent_agent.brief_of(report).read_text()
