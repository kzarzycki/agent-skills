"""omnigent_agent.py start refuses a role child a workspace a live session uses on its host (#750)."""

from pathlib import Path

import pytest
from test_omnigent_agent import (  # noqa: F401  (the fixtures apply here by name)
    FakeOmnigent,
    no_model,
    no_sleep,
    omnigent_agent,
)

WORKER = "engineering/skills/engineering-loop/worker.md"


def lead_in(og: FakeOmnigent, place: Path, **fields: object) -> None:
    """A live session this script did not start, using ``place`` on this host."""
    og.others.append(
        {"id": "lead", "title": "s750-lead", "host_id": og.host_id, "workspace": str(place)}
        | fields
    )


def start(og: FakeOmnigent, workspace: Path, **kwargs: object) -> str:
    kwargs.setdefault("role", WORKER)
    return omnigent_agent.start(
        og,
        str(kwargs.pop("agent", "claude")),
        str(kwargs.pop("title", "s750-worker")),
        "do X",
        workspace / "tmp" / "loop" / f"{kwargs.pop('report', 'r')}.md",
        confirm_seconds=0,
        workspace=str(workspace),
        **kwargs,
    )[0]


@pytest.mark.parametrize("top_level", [False, True])
def test_a_role_start_on_a_workspace_a_live_session_uses_is_refused_naming_it(
    tmp_path: Path, top_level: bool
) -> None:
    og = FakeOmnigent()
    first = start(og, tmp_path, title="s750-gate-a", report="a")
    with pytest.raises(omnigent_agent.Fail) as refused:
        start(og, tmp_path, title="s750-gate-b", report="b", top_level=top_level)
    assert f"live session {first} s750-gate-a" in str(refused.value)
    assert "its own worktree" in str(refused.value)
    assert list(og.sessions) == [first]  # refused before any session exists


def test_a_child_is_refused_the_workspace_its_own_parent_uses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_RUNNER_PRIMARY_SESSION_ID", "lead")
    og = FakeOmnigent()
    lead_in(og, tmp_path)
    with pytest.raises(omnigent_agent.Fail, match="live session lead s750-lead"):
        start(og, tmp_path)


def test_the_cli_exits_non_zero_on_a_used_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("do X")
    og = FakeOmnigent()
    lead_in(og, tmp_path)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    argv = ["start", "claude", "s750-worker", "b.md", "r.md", "--role", WORKER]
    assert omnigent_agent.main([*argv, "--top-level", "--confirm-seconds", "0"]) != 0
    assert "live session lead s750-lead" in capsys.readouterr().err


def test_the_same_start_succeeds_once_that_session_is_archived(tmp_path: Path) -> None:
    og = FakeOmnigent()
    first = start(og, tmp_path, title="s750-gate-a", report="a")
    og.archive(first)
    assert start(og, tmp_path, title="s750-gate-b", report="b") != first


@pytest.mark.parametrize(
    "fields",
    [{"status": "failed"}, {"archived": True}, {"host_id": "other"}, {"workspace": "/elsewhere"}],
)
def test_a_failed_or_archived_session_or_one_elsewhere_holds_no_workspace(
    tmp_path: Path, fields: dict
) -> None:
    og = FakeOmnigent()
    lead_in(og, tmp_path, **fields)
    assert start(og, tmp_path) == "s0"


def test_a_session_on_another_host_holds_that_host_s_workspace_not_this_one_s(
    tmp_path: Path,
) -> None:
    og = FakeOmnigent()
    lead_in(og, tmp_path, host_id="other")
    with pytest.raises(omnigent_agent.Fail, match="on host other by live session lead"):
        start(og, tmp_path, host_id="other", top_level=True)


def test_a_path_through_a_symlink_on_this_host_is_the_same_workspace(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    og = FakeOmnigent()
    lead_in(og, tmp_path / "link")
    with pytest.raises(omnigent_agent.Fail, match="live session lead"):
        start(og, tmp_path / "real")


def test_a_start_without_a_role_shares_a_used_workspace(tmp_path: Path) -> None:
    og = FakeOmnigent()
    lead_in(og, tmp_path)
    assert start(og, tmp_path, role=None, top_level=True) == "s0"


def test_a_cloud_agent_s_role_start_shares_a_used_workspace(tmp_path: Path) -> None:
    og = FakeOmnigent()
    og.harnesses["claude-cloud"] = omnigent_agent.CLOUD_HARNESS
    lead_in(og, tmp_path)
    first = start(og, tmp_path, agent="claude-cloud", title="s750-cloud-a", report="a")
    assert start(og, tmp_path, agent="claude-cloud", title="s750-cloud-b", report="b") != first
