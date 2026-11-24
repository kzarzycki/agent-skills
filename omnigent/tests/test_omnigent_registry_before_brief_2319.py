"""omnigent_agent.py: ``start`` writes its registry line when the session exists, before the brief is sent, and a
bad ``created_at`` skips one session in the console's adoption sweep, not the sweep (#2319)."""

import time
from pathlib import Path

import pytest
import test_omnigent_agent as base  # the faked server
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent


class SlowFirstTurn(base.FakeOmnigent):
    """Records the registry's text at the moment the brief is sent: a slow cold start confirms it past the
    adoption grace, so the line must already be there."""

    def __init__(self, registry: Path) -> None:
        super().__init__()
        self.registry, self.seen = registry, []

    def send(self, sid: str, text: str) -> None:
        self.seen.append(self.registry.read_text() if self.registry.exists() else "")
        super().send(sid, text)


def test_a_top_level_start_writes_its_registry_line_before_the_brief_is_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, brief = tmp_path / "leads.registry", tmp_path / "b.md"
    og = SlowFirstTurn(registry)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    brief.write_text("do X")
    argv = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--top-level"]
    assert omnigent_agent.main([*argv, "--registry", str(registry)]) == 0
    [before_brief] = og.seen
    assert before_brief.startswith("s0=") and "\tfollow" in before_brief
    assert registry.read_text().count("s0=") == 1  # armed again after the start: one line


def test_an_abandoned_start_takes_its_registry_line_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, brief = tmp_path / "leads.registry", tmp_path / "b.md"
    og = base.FakeOmnigent(deaf={0})  # s0 never takes the brief: abandoned, s1 is the retry
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.chdir(tmp_path)
    brief.write_text("do X")
    argv = ["start", "claude", "t", str(brief), str(tmp_path / "a.md"), "--top-level"]
    omnigent_agent.main([*argv, "--registry", str(registry), "--confirm-seconds", "0"])
    lines = registry.read_text().splitlines()
    assert [ln.split("=")[0] for ln in lines] == ["s1"]


def test_a_bad_created_at_skips_that_session_and_the_sweep_adopts_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_omnigent_adopt_leads import adopted, lead_row

    odd, fine = "a" * 32, "b" * 32
    registry = tmp_path / "leads.registry"
    registry.write_text("")
    og = base.Leads(**{odd: [base.told("brief", 60)], fine: [base.told("brief", 60)]})
    old = time.time() - omnigent_agent.ADOPT_GRACE_SECONDS - 5
    og.rows = [lead_row(odd, created_at="yesterday"), lead_row(fine, created_at=old)]
    base.supervised(og, registry, monkeypatch, 2, console=True)
    assert [e["session"] for e in adopted(registry)] == [fine]
    assert odd not in registry.read_text()
