"""omnigent_agent.py: a claude-cloud start takes `auto` from the command line only (#1632)."""

from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent


def cloud() -> base.FakeOmnigent:
    og = base.FakeOmnigent()
    og.harnesses = {"claude-cloud": omnigent_agent.CLOUD_HARNESS}
    return og


def test_auto_from_the_environment_alone_starts_a_cloud_worker_in_bypass_and_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OMNIGENT_PERMISSION_MODE", "auto")
    og = cloud()
    omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, top_level=True
    )
    assert og.modes["s0"] == "bypassPermissions"
    err = capsys.readouterr().err
    assert "OMNIGENT_PERMISSION_MODE=auto is not applied" in err
    assert "pass --permission-mode auto" in err


def test_only_the_flag_starts_a_cloud_worker_in_auto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OMNIGENT_PERMISSION_MODE", "auto")
    og = cloud()
    omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, permission_mode="auto"
    )
    assert og.modes["s0"] == "auto"
    assert "not applied" not in capsys.readouterr().err


def test_bypass_from_the_environment_starts_a_cloud_worker_quietly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OMNIGENT_PERMISSION_MODE", "bypassPermissions")
    og = cloud()
    omnigent_agent.start(og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.modes["s0"] == "bypassPermissions"
    assert "not applied" not in capsys.readouterr().err


def test_start_prints_the_mode_the_session_record_names_not_the_one_it_asked_for(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OMNIGENT_PERMISSION_MODE", raising=False)
    og = cloud()
    info = og.info
    og.info = lambda s: {**info(s), "permission_mode": "auto"}  # type: ignore[method-assign]
    omnigent_agent.start(og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0)
    assert og.modes["s0"] == "bypassPermissions"  # asked for
    assert "session s0: permission mode auto" in capsys.readouterr().err  # got


@pytest.mark.parametrize(
    ("record", "mode"),
    [
        ({"permission_mode": "bypassPermissions"}, "bypassPermissions"),
        ({"labels": {"omnigent.acp.permission_mode": "auto"}}, "auto"),
        ({"metadata": {"omnigent.acp.permission_mode": "auto"}}, "auto"),
        ({"terminal_launch_args": ["--permission-mode", "plan", "--x"]}, "plan"),
        (
            {"terminal_launch_args": ["--dangerously-bypass-approvals-and-sandbox"]},
            "bypassPermissions",
        ),
        ({"terminal_launch_args": ["--dangerously-skip-permissions"]}, "bypassPermissions"),
        ({}, "not named in the session record (the harness default)"),
    ],
)
def test_granted_mode_reads_each_place_a_session_record_names_its_mode(
    record: dict, mode: str
) -> None:
    assert omnigent_agent.granted_mode(record) == mode


class NoBypassToHand(base.FakeOmnigent):
    """A server whose caller runs in no bypass: it refuses a bypass create, as Omnigent does
    (kzarzycki/omnigent#526), and makes any other."""

    def create(self, agent: str, title: str, *args: object, **kw: object) -> str:
        names = ("model", "top_level", "workspace", "permission_mode")
        mode = dict(zip(names, args)).get("permission_mode", kw.get("permission_mode"))
        if mode == "bypassPermissions":
            from email.message import Message
            from urllib.error import HTTPError

            error = HTTPError("http://x/v1/sessions", 400, "Bad Request", Message(), None)
            raise omnigent_agent.Fail(
                "POST /v1/sessions: HTTP 400 Bad Request: a session created by another session"
                " cannot use permission mode bypassPermissions"
            ) from error
        return super().create(agent, title, *args, **kw)


@pytest.mark.parametrize("top_level", [False, True])
def test_a_refused_bypass_fails_the_start_loudly_and_never_falls_back_to_auto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, top_level: bool
) -> None:
    monkeypatch.setenv("OMNIGENT_PERMISSION_MODE", "auto")
    og = NoBypassToHand()
    og.harnesses = {"claude-cloud": omnigent_agent.CLOUD_HARNESS}
    with pytest.raises(omnigent_agent.Fail) as refused:
        omnigent_agent.start(
            og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, top_level=top_level
        )
    assert "only for a session that runs in bypassPermissions itself" in str(refused.value)
    assert "pass --permission-mode auto" in str(refused.value)
    assert og.modes == {}  # no session made, in auto or any other mode
    # the flag is the one way to a worker in auto, and this server makes it
    omnigent_agent.start(
        og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0, permission_mode="auto"
    )
    assert og.modes == {"s0": "auto"}


@pytest.mark.parametrize("top_level", [False, True])
def test_the_real_create_sends_the_cloud_default_as_the_session_s_mode(
    monkeypatch: pytest.MonkeyPatch, top_level: bool
) -> None:
    monkeypatch.setattr(omnigent_agent, "own_id", lambda: "")
    monkeypatch.setattr(omnigent_agent, "parent_id", lambda: "p" if not top_level else None)
    calls = base._agent_server(
        monkeypatch,
        {
            "/v1/projects": {"data": []},
            "/v1/sessions": {"id": "s1"},
            "/v1/sessions/p": {"id": "p"},
        },
    )
    monkeypatch.setattr(
        omnigent_agent.Omnigent,
        "agent",
        lambda self, name: {"id": name, "harness": omnigent_agent.CLOUD_HARNESS},
    )
    omnigent_agent.Omnigent().create(
        "claude-cloud", "t", top_level=top_level, permission_mode="bypassPermissions"
    )
    body = calls[-1][2]
    assert body["permission_mode"] == "bypassPermissions"
    assert ("parent_session_id" in body) is not top_level


def test_an_unsupported_mode_from_the_environment_names_the_flags_a_cloud_start_takes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OMNIGENT_PERMISSION_MODE", "plan")
    omnigent_agent.start(cloud(), "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0)
    err = capsys.readouterr().err
    assert "OMNIGENT_PERMISSION_MODE=plan is not applied" in err
    assert "takes --permission-mode auto or bypassPermissions alone" in err
    assert "--permission-mode plan" not in err


def test_an_unread_record_reports_its_mode_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OMNIGENT_PERMISSION_MODE", raising=False)
    og = cloud()

    def unreadable(sid: str) -> dict:
        raise omnigent_agent.Fail("GET: HTTP 503")

    og.info = unreadable  # type: ignore[method-assign]
    omnigent_agent.start(og, "claude-cloud", "t", "do X", tmp_path / "r.md", None, 0)
    assert "permission mode unknown (its record could not be read)" in capsys.readouterr().err
