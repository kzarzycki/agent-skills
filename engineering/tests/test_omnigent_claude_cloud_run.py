"""`claude-cloud-run` runs one command in a Claude cloud session on the checkout's pushed HEAD and exits with
its code; a host child is told the heavy-run hook's prefix, a cloud one is not (#1233)."""

import subprocess
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

FAILED = omnigent_agent.CLOUD_RUN_FAILED


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(checkout: Path, name: str) -> str:
    (checkout / name).write_text(name)
    git("add", name, cwd=checkout)
    git("commit", "-qm", name, cwd=checkout)
    return git("rev-parse", "HEAD", cwd=checkout)


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A checkout of a bare remote, its branch ``main`` pushed, with no environment lookup."""
    remote = tmp_path / "remote.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    work = tmp_path / "work"
    git("clone", "-q", f"file://{remote}", str(work), cwd=tmp_path)
    git("config", "user.email", "t@example.com", cwd=work)
    git("config", "user.name", "t", cwd=work)
    git("checkout", "-qb", "main", cwd=work)
    commit(work, "a.txt")
    git("push", "-q", "-u", "origin", "main", cwd=work)
    monkeypatch.setattr(
        omnigent_agent, "resolve_environment", lambda env, repo: ("env_1", "the-env")
    )
    for name in ("CLAUDE_CODE_REMOTE", "LOOP_DENY_LIST", "OMNIGENT_MODEL_CLAUDE_CLOUD_RUN"):
        monkeypatch.delenv(name, raising=False)
    return work


def cloud(monkeypatch: pytest.MonkeyPatch, reply: str) -> CloudFake:
    og = CloudFake(reply=reply)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda *a: og)
    return og


def cloud_run(checkout: Path, *command: str) -> int:
    return omnigent_agent.main(
        ["claude-cloud-run", "--checkout", str(checkout), "--timeout", "30", "--", *command]
    )


@pytest.mark.parametrize("unpushed", [False, True])
def test_it_refuses_tracked_changes_and_an_unpushed_head_before_any_session_exists(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    unpushed: bool,
) -> None:
    og = cloud(monkeypatch, "REPORT\nEXIT: 0")
    if unpushed:
        commit(checkout, "b.txt")
    else:
        (checkout / "a.txt").write_text("changed")
    assert cloud_run(checkout, "pytest") == FAILED
    err = capsys.readouterr().err
    assert "git push" in err
    assert ("is not on origin/main" if unpushed else "has tracked changes (a.txt)") in err
    assert "LOOP_HOST_RUN=<reason> pytest" in err  # the host fallback too (verifier m4)
    assert og.sessions == {}  # no session was made
    assert not (checkout / ".worktrees").exists()


def test_it_runs_the_command_with_the_cheap_model_auto_and_no_keep_and_exits_with_its_code(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = cloud(monkeypatch, "REPORT\nEXIT: 3\n5 passed, 3 failed\nFAILED tests/test_a.py::test_x")
    launched: list[list[str]] = []
    real = omnigent_agent.command
    monkeypatch.setattr(
        omnigent_agent, "command", lambda argv, ended: launched.append(argv) or real(argv, ended)
    )
    head = git("rev-parse", "HEAD", cwd=checkout)
    assert cloud_run(checkout, "uv run pytest -q") == 3
    run = launched[1]  # the first is claude-cloud-run's own
    assert run[:2] == ["run", "claude-cloud"]
    place = checkout / ".worktrees" / "claude-cloud-run-main"
    assert run[run.index("--workspace") + 1] == str(place)
    assert "--no-keep" in run
    assert run[run.index("--model") + 1] == "haiku"
    assert run[run.index("--permission-mode") + 1] == "bypassPermissions"
    brief = omnigent_agent.text_of(og.sessions["s0"][1])
    assert f"git checkout --detach {head}" in brief and "```sh\nuv run pytest -q\n```" in brief
    assert "`EXIT: <n>`" in brief
    assert og.overrides["s0"] == "haiku" and og.archived == ["s0"]  # finished: --no-keep
    out = capsys.readouterr().out
    report = Path(run[4])
    assert report.read_text().startswith("EXIT: 3") and str(report) in out
    assert f"exited 3 on {head[:12]}" in out


def test_a_second_run_reuses_the_launch_dir_and_points_it_at_the_new_head(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cloud(monkeypatch, "REPORT\nEXIT: 0\n1 passed")
    made: list[Path] = []
    real = omnigent_agent.launch_dir
    monkeypatch.setattr(
        omnigent_agent,
        "launch_dir",
        lambda remote, branch, env, path, **kw: (
            made.append(path) or real(remote, branch, env, path, **kw)
        ),
    )
    assert cloud_run(checkout, "pytest") == 0
    place = checkout / ".worktrees" / "claude-cloud-run-main"
    head = commit(checkout, "b.txt")
    git("push", "-q", cwd=checkout)
    assert cloud_run(checkout, "pytest", "-q") == 0
    assert made == [place]  # made once, then reused
    assert git("rev-parse", "HEAD", cwd=place) == head
    assert not (place / "a.txt").exists()  # still no files checked out


def test_a_failed_launch_exits_with_its_own_code_and_prints_the_host_fallback(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    og = cloud(monkeypatch, "REPORT\nEXIT: 0")
    og.fail.add("send")
    assert cloud_run(checkout, "mise run check") == FAILED
    err = capsys.readouterr().err
    assert "the cloud session gave no result" in err
    assert "LOOP_HOST_RUN=<reason> mise run check" in err


def test_the_model_variable_names_another_model(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = cloud(monkeypatch, "REPORT\nEXIT: 0")
    monkeypatch.setenv("OMNIGENT_MODEL_CLAUDE_CLOUD_RUN", "sonnet")
    assert cloud_run(checkout, "pytest") == 0
    assert og.overrides["s0"] == "sonnet"


def test_a_report_without_an_exit_line_is_a_failed_route_not_a_pass(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cloud(monkeypatch, "REPORT\nEXIT: none, the clone had no such commit")
    assert cloud_run(checkout, "pytest") == FAILED
    assert "names no `EXIT: <n>` line" in capsys.readouterr().err


def test_a_host_child_is_told_the_prefix_and_a_cloud_child_or_a_lead_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    note = "`LOOP_HOST_RUN=placed `"
    og = FakeOmnigent()
    child = tmp_path / "child.md"
    omnigent_agent.start(og, "claude", "t", "do X", child, None, 0)
    assert note in omnigent_agent.brief_of(child).read_text()
    lead = tmp_path / "lead.md"
    omnigent_agent.start(og, "claude", "l", "do X", lead, None, 0, top_level=True)
    assert note not in omnigent_agent.brief_of(lead).read_text()
    og = CloudFake()
    sid, _ = omnigent_agent.start(og, "claude-cloud", "c", "do X", tmp_path / "c.md", None, 0)
    assert note not in omnigent_agent.text_of(og.sessions[sid][1])


@pytest.mark.parametrize("where", ["client", "launch"])
def test_any_failure_of_the_route_exits_with_its_own_code_and_the_fallback(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    where: str,
) -> None:
    """The verifier's m3: an exception that is no Fail (a missing Omnigent config, a write that
    fails) is still the route's failure, never read as the command's exit 1."""

    def broken(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("~/.omnigent/config.yaml")

    if where == "client":
        monkeypatch.setattr(omnigent_agent, "Omnigent", broken)
    else:
        cloud(monkeypatch, "REPORT\nEXIT: 0")
        monkeypatch.setattr(omnigent_agent, "cloud_run_brief", broken)
    assert cloud_run(checkout, "pytest") == FAILED
    err = capsys.readouterr().err
    assert "FileNotFoundError" in err and "LOOP_HOST_RUN=<reason> pytest" in err


def test_with_pr_one_session_is_kept_and_later_runs_are_sent_to_it(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--pr N` starts a kept, PR-labelled session (`run --pr`, no `--no-keep`) and, while one is live, sends the run
    to it, so each head's gate is not a new VM, clone and build (#1595)."""
    launched: list[list[str]] = []

    def fake(argv: list[str], ended: dict[str, str]) -> int:
        launched.append(argv)
        report = next(a for a in argv if a.endswith(".md") and not a.endswith(".brief.md"))
        Path(report).write_text("EXIT: 0\nok\n")
        return 0

    live: list[str] = []
    real = omnigent_agent.command
    monkeypatch.setattr(
        omnigent_agent,
        "command",
        lambda argv, ended: (
            real(argv, ended) if argv[0] == "claude-cloud-run" else fake(argv, ended)
        ),
    )
    monkeypatch.setattr(omnigent_agent, "pr_workers", lambda og, pr=None: list(live))
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda *a: object())
    argv = [
        "claude-cloud-run",
        "--checkout",
        str(checkout),
        "--timeout",
        "30",
        "--pr",
        "5",
        "--",
        "pytest",
    ]
    assert omnigent_agent.main(argv) == 0
    first = launched[-1]
    assert first[0] == "run" and first[first.index("--pr") + 1] == "5" and "--no-keep" not in first
    live.append("s9")
    assert omnigent_agent.main(argv) == 0
    second = launched[-1]
    assert second[:2] == ["send", "s9"] and second[second.index("--pr") + 1] == "5"
    assert "--workspace" not in second
