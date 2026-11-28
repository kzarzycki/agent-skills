"""approvals.py land: after a landing that touches the cloud environment's setup script, the environment's copy is
checked against the base the PR merged into and the stale line printed; a diff that leaves the active script alone
makes no environment call (#989)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals

FAKE = """import json, sys
open(sys.argv[0] + ".called", "w").write(json.dumps(sys.argv[1:]))
print("environment setup is stale: dev (env_1); apply it with: cloud_verifier.py env-sync --apply")
sys.exit(1)
"""
MODERN, LEGACY = ".claude/claude-cloud-setup.sh", ".claude/cloud-setup.sh"


@pytest.fixture
def landed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """land_ended on a PR whose `files` are given; `git` records its fetches and answers `cat-file` from `present`
    (the setup scripts the fetched base holds); `called()` is the argv env-sync got, None when it was not run."""
    folder = tmp_path / "scripts"
    folder.mkdir()
    (folder / "cloud_verifier.py").write_text(FAKE)
    fetched: list[list[str]] = []
    present = {MODERN}
    monkeypatch.setattr(approvals, "installed_scripts", lambda skill: folder)
    monkeypatch.setattr(approvals, "loop_md", lambda: "")
    monkeypatch.setattr(approvals, "forge", lambda *a, **k: "origin")
    monkeypatch.setattr(approvals, "default_branch", lambda: "main")
    monkeypatch.setattr(approvals, "land_event", lambda *a, **k: None)
    real_run, real_popen = approvals.subprocess.run, approvals.subprocess.Popen

    def run(args, *a, **kw):
        if args[:2] == ["git", "fetch"]:
            fetched.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["git", "cat-file"]:
            path = args[3].split(":", 1)[1]
            return subprocess.CompletedProcess(args, 0 if path in present else 1, "", "")
        return real_run(args, *a, **kw)

    def popen(args, *a, **kw):  # land_ended's delayed ref clear: not started here
        return None if kw.get("start_new_session") else real_popen(args, *a, **kw)

    monkeypatch.setattr(approvals.subprocess, "run", run)
    monkeypatch.setattr(approvals.subprocess, "Popen", popen)
    approvals.landed_ok.clear()

    def pull(*paths: str, total: int | None = None, base: str = "main") -> dict[str, Any]:
        return {
            "number": 7,
            "headRefName": "claude/x",
            "baseRefName": base,
            "files": {"nodes": [{"path": p} for p in paths], "totalCount": total or len(paths)},
        }

    def called() -> list[str] | None:
        mark = folder / "cloud_verifier.py.called"
        return json.loads(mark.read_text()) if mark.exists() else None

    return {"pull": pull, "called": called, "fetched": fetched, "present": present}


def test_a_landing_that_touches_the_setup_script_prints_the_stale_line(landed, capsys) -> None:
    approvals.land_ended(landed["pull"]("README.md", MODERN))
    assert "environment setup is stale" in capsys.readouterr().out
    assert landed["called"]() == ["env-sync", "--script", MODERN, "--base", "origin/main"]


def test_a_landing_that_leaves_the_setup_script_alone_makes_no_environment_call(landed) -> None:
    approvals.land_ended(landed["pull"]("README.md", "src/app.py"))
    assert landed["called"]() is None


def test_the_check_reads_the_base_the_pr_merged_into_after_fetching_it(landed) -> None:
    """F1: a landing into a branch other than the default fetches that branch and names it, so a stale
    tracking ref is never what the environment is compared with."""
    approvals.land_ended(landed["pull"](MODERN, base="release"))
    assert landed["fetched"] == [
        ["git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release"]
    ]
    assert landed["called"]()[-2:] == ["--base", "origin/release"]


def test_a_diff_that_changes_only_the_inactive_legacy_script_makes_no_call(landed) -> None:
    """F6: with both scripts on the base the modern one is active; the legacy one is not the environment's."""
    landed["present"].add(LEGACY)
    approvals.land_ended(landed["pull"](LEGACY))
    assert landed["called"]() is None


def test_the_legacy_script_is_active_when_it_is_the_only_one_the_base_has(landed) -> None:
    landed["present"].clear()
    landed["present"].add(LEGACY)
    approvals.land_ended(landed["pull"](LEGACY))
    assert landed["called"]()[:3] == ["env-sync", "--script", LEGACY]


def test_a_file_list_the_forge_cut_short_is_checked_rather_than_trusted(landed) -> None:
    """F4: 100 files listed of 101 changed, none of them the script: the script may be the one left out."""
    approvals.land_ended(landed["pull"]("a.py", total=101))
    assert landed["called"]() is not None


def test_a_project_names_its_setup_script_once_in_loop_md_and_a_failed_check_never_fails_the_landing(
    landed, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(approvals, "loop_md", lambda: "Cloud setup script: ci/vm.sh\n")
    approvals.land_ended(landed["pull"](MODERN))  # not the declared path
    assert landed["called"]() is None
    monkeypatch.setattr(
        approvals, "installed_scripts", lambda skill: (_ for _ in ()).throw(OSError("boom"))
    )
    approvals.landed_ok.clear()
    approvals.land_ended(landed["pull"]("ci/vm.sh"))  # raises inside: reported, not raised
    assert "setup-script check failed" in capsys.readouterr().err
