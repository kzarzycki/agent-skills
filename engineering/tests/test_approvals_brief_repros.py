"""A fresh verifier's brief lists each previous finding's rerun command from the PR's evidence branch `verify/pr-<N>`
(#1595), so no report file is handed between passes and a verifier on any host reruns them. The remote is a local bare
repository, so the branch is really pushed and fetched."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from approvals_harness import LOOP, approvals, pull, verdict_on

FINDING = "**Verifier (codex), pass 1 · F1** (major): a gap\n\nit fails"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_fresh_brief_lists_each_findings_rerun_command_from_the_evidence_branch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    monkeypatch.chdir(clone)
    repro, log = tmp_path / "r.sh", tmp_path / "l.txt"
    repro.write_text("uv run pytest tests/test_x.py -k gap\n")
    log.write_text("FAILED\n")
    sha, written, asset = approvals.write_evidence(7, 1, "a gap", repro, log)
    assert written == ["pass-1/a-gap/repro.sh", "pass-1/a-gap/log.txt"] and asset is None
    found = pull(
        body="Closes #12.\n", reviews=(verdict_on("c" * 40, heading="Verifier (codex), pass 1"),)
    )
    found["reviewThreads"] = {
        "nodes": [{"isResolved": False, "comments": {"nodes": [{"body": FINDING}]}}]
    }
    monkeypatch.setattr(approvals, "pull_request", lambda _n: found)
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: "b" * 40)
    monkeypatch.setattr(approvals, "project", lambda: (None, LOOP))
    assert approvals.main(["brief", "7"]) == 0
    out = capsys.readouterr().out
    assert "     Rerun: bash pass-1/a-gap/repro.sh\n" in out
    assert f"- Evidence: branch verify/pr-7 at {sha}" in out
    assert "<details>" not in out and "FAILED" not in out  # the log stays on the branch
