"""This repo's own docs/agents/ files parse with the approvals.py it ships, so a settings change that leaves them
behind fails here instead of refusing every land in this repo (#548)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
AGENTS = REPOSITORY / "docs" / "agents"
SPEC = importlib.util.spec_from_file_location(
    "approvals",
    REPOSITORY / "engineering" / "skills" / "engineering-loop" / "scripts" / "approvals.py",
)
assert SPEC and SPEC.loader
approvals = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(approvals)


def test_this_repos_loop_and_tracker_settings_parse() -> None:
    """A refusal raises approvals.Refused with the reader's own message, which fails the test."""
    assert approvals.settings((AGENTS / "loop.md").read_text())
    # settings() takes any string for `gate`; gate() is what land and local-ci refuse a malformed one with
    assert approvals.gate()[1]
    tracker = (AGENTS / "issue-tracker.md").read_text()
    assert approvals.tracker_settings(tracker)
    assert approvals.label_names(tracker)["component"]
