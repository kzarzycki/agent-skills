"""This repo's own docs/agents/ files parse with the approvals.py it ships and with the copy installed under
.claude/skills, which is what lands this repo's PRs, so a settings change either copy can't read fails here instead
of refusing every land in this repo (#548, #613)."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
# The shipped gatekeeper is its own package's; a release before the package split installed it in engineering-loop.
COPIES = {
    copy: next(
        path
        for folder in ("gatekeeper", "engineering-loop")
        for name in ("gatekeeper.py", "approvals.py")
        if (path := root / "skills" / folder / "scripts" / name).exists()
    )
    for copy, root in (
        ("shipped", REPOSITORY / "gatekeeper"),
        ("installed", REPOSITORY / ".claude"),
    )
}


@pytest.mark.parametrize("copy", COPIES)
def test_this_repos_policy_and_tracker_settings_parse(copy: str, monkeypatch) -> None:
    """A refusal raises the copy's Refused with the reader's own message, which fails the test."""
    spec = importlib.util.spec_from_file_location(f"approvals_{copy}", COPIES[copy])
    assert spec and spec.loader
    approvals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(approvals)
    monkeypatch.setattr(approvals, "toplevel", lambda: REPOSITORY)
    try:
        tracker, policy = approvals.project()
    except approvals.Refused as refusal:
        # The installed pack is the released tag apm.yml pins, so a setting this repo's docs adopt before that tag
        # exists is unknown to it until the pin moves; skip on that alone, never on another refusal.
        if copy == "installed" and "unknown setting" in str(refusal):
            pytest.skip(f"the installed pack predates a setting the docs use: {refusal}")
        raise
    assert approvals.settings(policy)["risk"]["paths"]
    # settings() takes any string for `gate`; gate() is what local-ci refuses a malformed one with
    assert approvals.gate()[1]
    assert approvals.tracker_settings(tracker)
    assert approvals.label_names(tracker)["component"]
    # qualify's QUALIFY_TIMEOUT exit (vendoring/skills/vendoring/scripts/capability_pack/cli.py), so a gate timed out on a loaded host is a
    # machine fault local-ci refuses, never a red gate (#851)
    assert approvals.settings(policy).get("machine_exit") == 78


def test_hook_script_the_settings_name_is_tracked() -> None:
    """A fresh checkout must hold the script settings.json runs, or every Bash call fails (#1432)."""
    root = Path(__file__).resolve().parents[1]
    script = ".claude/hooks/engineering/hooks/heavy_run_guard.py"
    tracked = subprocess.run(
        ["git", "ls-files", script], cwd=root, capture_output=True, text=True, check=True
    )
    assert tracked.stdout.strip() == script
    # --no-index: git skips ignore rules for a tracked path, so the plain command passes with the ignore line back
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", ".claude/hooks"], cwd=root, check=False
    )
    assert ignored.returncode == 1, (
        ".claude/hooks/ is git-ignored: a later hook would miss a fresh checkout"
    )


def test_every_plugin_has_a_component() -> None:
    """`check build` refuses an issue with no listed `area:` label, so a plugin missing from `components` blocks
    every issue that touches only it (#2185)."""
    spec = importlib.util.spec_from_file_location("approvals_components", COPIES["shipped"])
    assert spec and spec.loader
    approvals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(approvals)
    tracker = (REPOSITORY / "docs/agents/issue-tracker.md").read_text()
    components = {
        name.removeprefix("area:") for name in approvals.label_names(tracker)["component"]
    }
    plugins = {path.parent.parent.name for path in REPOSITORY.glob("*/.claude-plugin/plugin.json")}
    assert plugins <= components, f"no component for: {sorted(plugins - components)}"
