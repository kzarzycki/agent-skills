"""`verdict` writes a boundary around each out-of-diff finding in the review's body, and `previous_findings` splits on it
(#1595), so a finding whose body has bullets, or whose evidence link is a bullet, keeps its link and its rerun command.
The review body is built by the real `verdict`; only GitHub's posting is stubbed."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import HEAD, approvals


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_finding_with_bullets_and_a_bullet_link_keeps_its_rerun_through_the_real_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    monkeypatch.chdir(clone)
    repro, log = tmp_path / "r.sh", tmp_path / "l.txt"
    repro.write_text("echo actually ran\n")
    log.write_text("ok\n")
    sha, [path, _], _ = approvals.write_evidence(7, 1, "gap", repro, log)
    report = tmp_path / "report.md"
    report.write_text(
        "# Verifier report: PR #7, pass 1\n\nVerifier: claude, same-family, pass 1\n\n## Criteria\n\n- a criterion\n\n"
        "## Correctness\n\n### S1 (major) docs/old.md:3: a gap outside the diff\n\n"
        f"- Failing input: a draft.\n- Evidence: https://example.test/blob/{sha}/{path}\n\n"
        "### S2 (minor) docs/old.md:9: another\n\nThe doc.\n\n"
        f"Head: {HEAD}\nVERDICT: 0 blocker, 1 major, 1 minor\nSATISFIED: no\nRisk: low — a test fixture\n"
    )
    posted: list[dict[str, Any]] = []
    monkeypatch.setattr(approvals, "pull_request", lambda _n: {"baseRefOid": "b" * 40})
    monkeypatch.setattr(approvals, "diff_lines", lambda base, head: {})
    monkeypatch.setattr(approvals, "post_review", lambda pr, review: posted.append(review))
    assert approvals.main(["verdict", "7", str(report)]) == 0
    first, second = approvals.previous_findings({"reviews": {"nodes": [posted[0]]}}, 1)
    assert "Evidence: https://example.test/blob/" in first and "another" not in first
    assert second.startswith("**Verifier (claude, same-family), pass 1 · S2**")
    command = approvals.rerun_command(7, first)
    assert command is not None
    ran = subprocess.run(
        command, shell=True, cwd=clone, capture_output=True, text=True, check=False
    )
    assert (ran.returncode, ran.stdout.strip()) == (0, "actually ran"), ran.stderr
