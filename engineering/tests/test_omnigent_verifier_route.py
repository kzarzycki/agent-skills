"""omnigent_agent.py: the verifier's fallback routes, one switch on the start (#890)."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from test_omnigent_agent import FakeOmnigent, omnigent_agent


def route(name: str, **given: str | bool | None) -> argparse.Namespace:
    args = argparse.Namespace(
        verifier_route=name,
        agent="codex",
        host=None,
        model=None,
        author_model=None,
        permission_mode=None,
        same_family=False,
    )
    for key, value in given.items():
        setattr(args, key, value)
    return args


def test_gemini_route_runs_agy_unattended_on_a_named_host() -> None:
    args = route("gemini", host="kris")
    omnigent_agent.apply_route(args)
    assert (args.agent, args.permission_mode) == ("antigravity-native-ui", "bypassPermissions")
    with pytest.raises(omnigent_agent.Fail, match="pass --host"):
        omnigent_agent.apply_route(route("gemini"))


def test_claude_route_is_same_family_on_another_model_than_the_author_s() -> None:
    args = route("claude", model="claude-opus-5-5", author_model="claude-sonnet-5-5")
    omnigent_agent.apply_route(args)
    assert (args.agent, args.same_family) == ("claude", True)
    with pytest.raises(omnigent_agent.Fail, match="pass --model"):
        omnigent_agent.apply_route(route("claude"))
    with pytest.raises(omnigent_agent.Fail, match="different --model"):
        omnigent_agent.apply_route(route("claude", model="x", author_model="x"))


def test_signature_names_agy() -> None:
    assert (
        omnigent_agent.signature("antigravity-native", "gemini-4-hydrogen-medium", None)
        == "agy/gemini-4-hydrogen-medium/?"
    )


def test_gemini_route_without_a_host_is_refused_by_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    brief = tmp_path / "b.md"
    brief.write_text("review")
    monkeypatch.setattr(omnigent_agent, "Omnigent", FakeOmnigent)
    monkeypatch.chdir(tmp_path)
    argv = ["run", "codex", "t", str(brief), str(tmp_path / "r.md"), "--role", "verifier.md"]
    assert omnigent_agent.main([*argv, "--verifier-route", "gemini"]) == 1
    assert "pass --host" in capsys.readouterr().err


def test_agy_on_another_host_reads_its_brief_from_a_file_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.host = lambda n: {"kris": "far"}[n]  # type: ignore[method-assign]
    og.host_names = {"far": "kris"}
    og.harnesses = {"antigravity-native-ui": "antigravity-native"}
    written: dict[str, str] = {}
    og.filesystem = lambda sid, path, method, body=None: written.update({path: body["content"]})  # type: ignore[attr-defined]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("review the head " * 400)
    argv = ["start", "antigravity-native-ui", "t", "b.md", "/there/r.md", "--top-level"]
    argv += ["--host", "kris", "--workspace", "/there", "--permission-mode", "bypassPermissions"]
    assert omnigent_agent.main(argv) == 0
    sent = [omnigent_agent.text_of(i) for i in og.sessions["s0"] if i.get("role") == "user"]
    assert sent == ["Work on t: read /there/r.md.brief and do what it says."], sent
    assert "review the head" in written["/there/r.md.brief"]
