"""This repo's own docs/agents/ files parse with the approvals.py it ships and with the copy installed under
.claude/skills, which is what lands this repo's PRs, so a settings change either copy can't read fails here instead
of refusing every land in this repo (#548, #613)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = Path("skills") / "engineering-loop" / "scripts" / "approvals.py"
COPIES = {
    "shipped": REPOSITORY / "engineering" / SCRIPT,
    "installed": REPOSITORY / ".claude" / SCRIPT,
}


@pytest.mark.parametrize("copy", COPIES)
def test_this_repos_policy_and_tracker_settings_parse(copy: str, monkeypatch) -> None:
    """A refusal raises the copy's Refused with the reader's own message, which fails the test."""
    spec = importlib.util.spec_from_file_location(f"approvals_{copy}", COPIES[copy])
    assert spec and spec.loader
    approvals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(approvals)
    monkeypatch.setattr(approvals, "toplevel", lambda: REPOSITORY)
    tracker, policy = approvals.project()
    assert approvals.settings(policy)["risk"]["paths"]
    assert approvals.tracker_settings(tracker)
    assert approvals.label_names(tracker)["component"]
