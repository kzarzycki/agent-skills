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


def agy_info(og: FakeOmnigent) -> None:
    og.info = lambda s: {"id": s, "status": "failed", "harness": "antigravity-native"}  # type: ignore[method-assign]


def test_a_quota_banner_fails_the_turn_with_the_reset_time(tmp_path: Path) -> None:
    og = FakeOmnigent()
    agy_info(og)
    sid = og.create("antigravity-native-ui", "t")
    og.sessions[sid].append({"type": "error", "content": [{"type": "text", "text": BANNER}]})
    before = time.time()
    with pytest.raises(omnigent_agent.Fail) as e:
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=5)
    assert "129h55m" in str(e.value) and "quota is out" in str(e.value)
    until = omnigent_agent.agy_quota_until(before)
    assert until is not None and abs(until - (before + 129 * 3600 + 55 * 60)) < 120


PANE = """\
  > review the head

Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 129h5m17s.
Error ID: 5b0e1c9e-6f3a-4d8e-9a53-0c1f2b7d4e11-1
"""


def test_a_banner_only_in_the_pane_fails_a_silent_agy_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    og.harnesses = {"antigravity-native-ui": "antigravity-native"}
    sid = og.create("antigravity-native-ui", "t")
    og.sessions[sid].append(  # the brief, and no assistant item: the history holds nothing else
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "text", "text": "review"}],
            "created_at": time.time() - 2 * omnigent_agent.AGY_SILENT_SECONDS,
        }
    )
    monkeypatch.setattr(
        og, "info", lambda s: {"id": s, "status": "running", "harness": "antigravity-native"}
    )
    reads = iter(["", PANE])  # empty when the wait attaches, the banner after
    monkeypatch.setenv("OMNIGENT_AGY_PANE_CMD", "unused")
    monkeypatch.setattr(omnigent_agent, "agy_pane", lambda s: next(reads, PANE))
    before = time.time()
    with pytest.raises(omnigent_agent.Fail) as e:
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=5)
    assert "129h5m17s" in str(e.value)
    until = omnigent_agent.agy_quota_until(before)
    assert until is not None and abs(until - (before + 129 * 3600 + 5 * 60 + 17)) < 120


def test_a_young_agy_session_is_not_read_at_its_pane(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    og = FakeOmnigent()
    sid = og.create("claude", "t")
    og.sessions[sid].append({"type": "message", "role": "user", "created_at": time.time()})
    info = {"harness": "antigravity-native"}
    monkeypatch.setattr(omnigent_agent, "agy_pane", lambda s: PANE)
    assert omnigent_agent.agy_silent_banner(sid, info, og.items(sid)) is None


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


def test_other_harnesses_phrases_and_quotes_are_no_banner() -> None:
    now = time.time()
    assert omnigent_agent.agy_quota_reset("the quota reached its limit. Resets in 1h", now) is None
    assert omnigent_agent.agy_quota_reset("Individual quota reached.", now) is None  # no reset time
    error = [{"type": "error", "content": [{"type": "text", "text": BANNER}]}]
    quoted = [
        {"type": "message", "role": "assistant", "content": [{"type": "text", "text": BANNER}]}
    ]
    agy, claude = {"harness": "antigravity-native"}, {"harness": "claude-native"}
    assert omnigent_agent.agy_quota_banner(claude, error) is None
    assert omnigent_agent.agy_quota_banner(agy, quoted) is None  # an assistant quoting the banner
    assert omnigent_agent.agy_quota_banner(agy, error) is not None


def test_an_old_banner_in_the_own_pane_is_no_new_hold(quota_file: Path) -> None:
    now = time.time()
    first = omnigent_agent.agy_banner(PANE, now, need_id=True)
    assert first is not None and first[2] == "5b0e1c9e-6f3a-4d8e-9a53-0c1f2b7d4e11-1"
    omnigent_agent.record_agy_quota(first[0], first[2])
    # read again later: the same banner keeps its first reset, not one counted from this read
    again = omnigent_agent.agy_banner(PANE, now + 3600, need_id=True)
    assert again is not None and again[0] == first[0]
    # after its reset the same banner left in scrollback is none
    assert omnigent_agent.agy_banner(PANE, first[0] + 1, need_id=True) is None
    # a pane banner with no Error ID (an agent quoting the text) is none
    assert omnigent_agent.agy_banner(PANE.split("Error ID")[0], now, need_id=True) is None


def silent_agy(tmp_path: Path) -> tuple[FakeOmnigent, str]:
    og = FakeOmnigent()
    sid = og.create("antigravity-native-ui", "t")
    og.sessions[sid].append(
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "text", "text": "review"}],
            "created_at": time.time() - 2 * omnigent_agent.AGY_SILENT_SECONDS,
        }
    )
    og.info = lambda s: {"id": s, "status": "running", "harness": "antigravity-native"}  # type: ignore[method-assign]
    return og, sid


def test_the_configured_pane_command_reaches_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pane, flag = tmp_path / "pane.txt", tmp_path / "flag"
    pane.write_text(PANE)
    # the pane is empty when the wait attaches (the first read), and shows the banner after
    monkeypatch.setenv(
        "OMNIGENT_AGY_PANE_CMD",
        f"if [ -e {flag} ]; then cat {pane}; else touch {flag}; fi # {{sid}}",
    )
    og, sid = silent_agy(tmp_path)
    with pytest.raises(omnigent_agent.Fail, match="129h5m17s"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=5)


def test_a_banner_already_in_the_pane_when_the_wait_attaches_is_no_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pane holds no timestamp: an old banner, its reset long past, is the same at every read (#2922 F1)."""
    pane = tmp_path / "pane.txt"
    pane.write_text(PANE)
    monkeypatch.setenv("OMNIGENT_AGY_PANE_CMD", f"cat {pane} # {{sid}}")
    og, sid = silent_agy(tmp_path)
    with pytest.raises(omnigent_agent.Fail, match="gave no report"):
        omnigent_agent.wait(og, sid, tmp_path / "r.md", timeout=1)
    assert omnigent_agent.agy_quota_until(time.time()) is None


def test_an_expired_banner_does_not_hide_a_fresh_one_in_the_same_capture() -> None:
    now = time.time()
    old = "Individual quota reached. Resets in 1h\nError ID: aaaaaaaa-1111-1\n"
    new = "Individual quota reached. Resets in 2h\nError ID: bbbbbbbb-2222-1\n"
    omnigent_agent.record_agy_quota(now - 60, "aaaaaaaa-1111-1")  # recorded, and past its reset
    found = omnigent_agent.agy_banner(old + "output\n" + new, now, need_id=True)
    assert found is not None and found[2] == "bbbbbbbb-2222-1"
    assert abs(found[0] - (now + 7200)) < 5
    # a banner among the IDs the wait attached to is not fresh
    assert omnigent_agent.agy_banner(new, now, need_id=True, baseline={"bbbbbbbb-2222-1"}) is None


def test_with_no_pane_command_nothing_is_read_and_the_silence_is_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OMNIGENT_AGY_PANE_CMD", raising=False)
    monkeypatch.setattr(omnigent_agent, "AGY_NOTED", set())

    def no_scan(*args: object, **kw: object) -> None:
        raise AssertionError("a pane was read with no command set")

    monkeypatch.setattr(omnigent_agent.subprocess, "run", no_scan)
    og, sid = silent_agy(tmp_path)
    assert omnigent_agent.agy_silent_banner(sid, og.info(sid), og.items(sid), set()) is None
    assert "OMNIGENT_AGY_PANE_CMD" in capsys.readouterr().err
