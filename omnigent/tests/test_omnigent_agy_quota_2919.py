"""omnigent_agent.py: an Antigravity quota banner fails the turn naming its reset, and holds gemini starts (#2919)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from test_omnigent_agent import FakeOmnigent, omnigent_agent

BANNER = "Individual quota reached for gemini-4-hydrogen-medium. Resets in 129h55m"


@pytest.fixture(autouse=True)
def quota_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "cache" / "agy-quota.json"
    monkeypatch.setattr(omnigent_agent, "agy_quota_path", lambda: path)
    monkeypatch.setattr(omnigent_agent.time, "sleep", lambda s: None)
    return path


def test_a_quota_banner_fails_the_turn_with_the_reset_time(tmp_path: Path) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    og.sessions[sid].append(
        {"type": "message", "role": "assistant", "content": [{"type": "text", "text": BANNER}]}
    )
    before = time.time()
    with pytest.raises(omnigent_agent.Fail) as e:
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=5)
    assert "129h55m" in str(e.value) and "quota is out" in str(e.value)
    until = omnigent_agent.agy_quota_until(before)
    assert until is not None and abs(until - (before + 129 * 3600 + 55 * 60)) < 120


def test_a_gemini_start_is_refused_until_the_recorded_reset_passes(
    tmp_path: Path,
    role_file: Callable[[str], str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    now = time.time()
    omnigent_agent.record_agy_quota(now + 3600)
    og = FakeOmnigent()
    og.harnesses = {"antigravity-native-ui": "antigravity-native"}
    og.host = lambda n: {"host": og.host_id}[n]  # type: ignore[method-assign]
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "b.md").write_text("review")
    argv = ["start", "codex", "t", "b.md", str(tmp_path / "r.md")]
    argv += ["--role", role_file("verifier.md"), "--verifier-route", "gemini", "--host", "host"]
    argv += ["--model", "gemini-4-hydrogen-medium"]
    assert omnigent_agent.main(argv) == 1
    err = capsys.readouterr().err
    assert "quota is out until" in err and "--verifier-route codex" in err
    assert og.sessions == {}
    omnigent_agent.agy_quota_path().write_text('{"until": %s}' % (now - 1))  # the reset has passed
    assert omnigent_agent.main(argv) == 0
    assert list(og.sessions) == ["s0"]
