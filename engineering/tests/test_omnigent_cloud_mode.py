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
