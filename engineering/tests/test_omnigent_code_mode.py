"""`start` and `run` launch a Claude session with code mode on: `--code-mode` (#1505)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_omnigent_agent import (  # noqa: F401  (the autouse fixtures apply by import)
    FakeOmnigent,
    _agent_server,
    no_loop_events,
    no_model,
    no_sleep,
    omnigent_agent,
    this_repo,
    trusted_folders,
)

HIDDEN = "Bash,Read,Edit,Write,Glob,Grep,NotebookEdit,WebFetch,WebSearch"


def settings(mode: str, plugin: str = "code-mode@claude-mods") -> list[str]:
    body = {"enabledPlugins": {plugin: True}, "env": {"OMNIGENT_CODE_MODE": mode}}
    return ["--settings", json.dumps(body)]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OMNIGENT_CODE_MODE",
        "OMNIGENT_CODE_MODE_PLUGIN",
        "OMNIGENT_PERMISSION_MODE",
        "CLAUDE_CONFIG_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """The calls the real `Omnigent.create` makes, against a faked server."""
    return _agent_server(
        monkeypatch,
        {
            "/v1/agents": [{"name": n, "id": a} for a, n in omnigent_agent.AGENTS.items()],
            "/v1/agents?scope=user": [],
            "/v1/projects": {"data": []},
            "/v1/sessions": {"id": "s1"},
        },
    )


def last(calls: list[tuple]) -> dict:
    """The body of the last session create in ``calls``."""
    return [c[2] for c in calls if c[:2] == ("POST", "/v1/sessions")][-1]


def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *plugins: str) -> Path:
    """A temporary Claude config dir whose installed plugins are ``plugins``."""
    config = tmp_path / "claude-config"
    (config / "plugins").mkdir(parents=True)
    listed = {p: [{"scope": "user", "installPath": f"/x/{p}"}] for p in plugins}
    (config / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": listed})
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    return config


def test_create_adds_the_plugin_settings_and_for_exclusive_hides_the_built_ins(
    calls: list[tuple],
) -> None:
    og = omnigent_agent.Omnigent()
    og.create("claude", "t", code_mode="exclusive")
    assert last(calls)["terminal_launch_args"] == [
        *settings("exclusive"),
        "--disallowedTools",
        HIDDEN,
    ]
    assert last(calls)["labels"] == {"omni.code_mode": "exclusive"}
    og.create("claude", "t", code_mode="preferred")
    assert last(calls)["terminal_launch_args"] == settings("preferred")
    assert last(calls)["labels"] == {"omni.code_mode": "preferred"}
    og.create("claude", "t")  # none: the session starts as before
    assert "terminal_launch_args" not in last(calls) and "labels" not in last(calls)


def test_the_disallowed_list_is_the_launcher_s_list_in_its_order() -> None:
    assert omnigent_agent.CODE_MODE_HIDDEN == HIDDEN


def test_code_mode_joins_the_permission_mode_and_lean_role_args_in_one_list(
    calls: list[tuple], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(omnigent_agent.Path, "home", lambda: tmp_path / "home")
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    lean = ["--strict-mcp-config", "--tools", omnigent_agent.LEAN_TOOLS]
    og = omnigent_agent.Omnigent()
    for role in ("worker", "verifier"):
        og.create(
            "claude",
            "t",
            workspace=str(repo),
            permission_mode="bypassPermissions",
            role=f"/x/engineering-loop/{role}.md",
            code_mode="exclusive",
        )
        assert last(calls)["terminal_launch_args"] == [
            "--permission-mode",
            "bypassPermissions",
            *lean,
            *settings("exclusive"),
            "--disallowedTools",
            HIDDEN,
        ]
        assert last(calls)["labels"] == {"omni.role": role, "omni.code_mode": "exclusive"}
    (repo / "docs" / "agents").mkdir(parents=True)
    (repo / "docs" / "agents" / "loop.md").write_text("# Loop\n\nLead autocompact: 150k\n")
    og.create("claude", "t", top_level=True, workspace=str(repo), code_mode="preferred")
    assert last(calls)["terminal_launch_args"] == ["--autocompact", "150k", *settings("preferred")]


def test_a_non_claude_agent_s_create_carries_no_code_mode(
    calls: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    og = omnigent_agent.Omnigent()
    og.create("codex", "t", role="/x/engineering-loop/verifier.md", code_mode="exclusive")
    assert "terminal_launch_args" not in last(calls)
    assert last(calls)["labels"] == {"omni.role": "verifier"}
    monkeypatch.setenv("OMNIGENT_CODE_MODE", "exclusive")
    og.create("codex", "t")
    assert "terminal_launch_args" not in last(calls) and "labels" not in last(calls)


def test_the_environment_is_the_default_and_the_flag_outranks_it(
    calls: list[tuple], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIGENT_CODE_MODE", "preferred")
    og = omnigent_agent.Omnigent()
    og.create("claude", "t")
    assert last(calls)["terminal_launch_args"] == settings("preferred")
    og.create("claude", "t", code_mode="exclusive")
    assert last(calls)["terminal_launch_args"][:2] == settings("exclusive")
    monkeypatch.setenv("OMNIGENT_CODE_MODE_PLUGIN", "other@market")
    og.create("claude", "t")
    assert last(calls)["terminal_launch_args"] == settings("preferred", "other@market")


def test_start_passes_the_mode_to_a_claude_create_once_the_plugin_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    installed(tmp_path, monkeypatch, "code-mode@claude-mods")
    og = FakeOmnigent()
    omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "r.md", None, 0, code_mode="exclusive"
    )
    monkeypatch.setenv("OMNIGENT_CODE_MODE", "preferred")
    omnigent_agent.start(og, "claude", "t2", "do X", tmp_path / "r.md", None, 0)
    assert og.code_modes == ["exclusive", "preferred"]
    assert "code mode" not in capsys.readouterr().err


def test_start_fails_before_any_session_when_the_plugin_is_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = installed(tmp_path, monkeypatch, "other@market")
    og = FakeOmnigent()
    with pytest.raises(
        omnigent_agent.Fail, match=r"run `claude plugin install code-mode@claude-mods`"
    ):
        omnigent_agent.start(
            og, "claude", "t", "do X", tmp_path / "r.md", None, 0, code_mode="exclusive"
        )
    monkeypatch.setenv("OMNIGENT_CODE_MODE", "preferred")
    with pytest.raises(omnigent_agent.Fail, match="claude plugin install"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    (config / "plugins" / "installed_plugins.json").unlink()  # none installed at all
    with pytest.raises(omnigent_agent.Fail, match="claude plugin install"):
        omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.sessions == {}
    # another plugin proves the path on a host without code-mode
    monkeypatch.setenv("OMNIGENT_CODE_MODE_PLUGIN", "other@market")
    installed(tmp_path / "again", monkeypatch, "other@market")
    omnigent_agent.start(og, "claude", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.code_modes == ["preferred"]


def test_the_check_reads_claude_s_home_without_claude_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(omnigent_agent.Path, "home", lambda: tmp_path / "home")
    listed = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    listed.parent.mkdir(parents=True)
    listed.write_text(json.dumps({"version": 2, "plugins": {}}))
    with pytest.raises(omnigent_agent.Fail, match=str(listed)):
        omnigent_agent.require_code_mode_plugin()
    listed.write_text(json.dumps({"version": 2, "plugins": {"code-mode@claude-mods": []}}))
    omnigent_agent.require_code_mode_plugin()


def test_another_host_is_not_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installed(tmp_path, monkeypatch)  # nothing installed here
    og = FakeOmnigent()
    monkeypatch.setattr(og, "loop_text", lambda *_: "", raising=False)
    omnigent_agent.start(
        og, "claude", "t", "do X", tmp_path / "r.md", None, 0, code_mode="exclusive", host_id="far"
    )
    assert og.code_modes == ["exclusive"]


def test_a_non_claude_start_names_an_explicit_flag_as_dropped_and_the_variable_stays_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    installed(tmp_path, monkeypatch)  # the check is a claude agent's only
    og = FakeOmnigent()
    omnigent_agent.start(
        og, "codex", "t", "do X", tmp_path / "r.md", None, 0, code_mode="preferred"
    )
    err = capsys.readouterr().err
    assert [line for line in err.splitlines() if "code mode" in line] == [
        "codex takes no code mode: --code-mode preferred was not applied"
    ]
    monkeypatch.setenv("OMNIGENT_CODE_MODE", "exclusive")
    omnigent_agent.start(og, "codex", "t2", "do X", tmp_path / "r.md", None, 0)
    assert "code mode" not in capsys.readouterr().err
    assert og.code_modes == [None, None]


@pytest.mark.parametrize("env", [True, False])
def test_a_bad_value_fails_before_any_session(
    env: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(tmp_path, monkeypatch, "code-mode@claude-mods")
    if env:
        monkeypatch.setenv("OMNIGENT_CODE_MODE", "on")
    flag = None if env else "on"
    source = "OMNIGENT_CODE_MODE" if env else "--code-mode"
    for agent in ("claude", "codex"):
        og = FakeOmnigent()
        with pytest.raises(omnigent_agent.Fail, match=f"{source} on: not a code mode"):
            omnigent_agent.start(og, agent, "t", "do X", tmp_path / "r.md", None, 0, code_mode=flag)
        assert og.sessions == {}


def test_the_script_takes_the_flag_on_start_and_run() -> None:
    script = Path(omnigent_agent.__file__)
    for cmd in ("start", "run"):
        out = subprocess.run(
            [sys.executable, str(script), cmd, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert out.returncode == 0 and "--code-mode exclusive|preferred" in out.stdout


def test_a_service_does_not_carry_the_mode() -> None:
    assert "OMNIGENT_CODE_MODE" not in omnigent_agent.SERVICE_VARIABLES


def test_the_command_line_flag_reaches_the_create_and_a_bad_one_starts_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    installed(tmp_path, monkeypatch, "code-mode@claude-mods")
    og = FakeOmnigent()
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(tmp_path)
    (tmp_path / "brief.md").write_text("do X")
    argv = ["start", "claude", "t", str(tmp_path / "brief.md"), "tmp/lead.md", "--top-level"]
    assert omnigent_agent.main([*argv, "--code-mode", "preferred"]) == 0
    assert og.code_modes == ["preferred"]
    assert omnigent_agent.main([*argv, "--code-mode", "always"]) == 1
    assert "--code-mode always: not a code mode" in capsys.readouterr().err
    assert len(og.sessions) == 1
