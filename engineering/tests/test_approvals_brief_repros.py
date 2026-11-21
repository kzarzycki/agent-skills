"""A fresh verifier's brief gives each open finding's rerun command, from the evidence link in the finding's text (#1595):
the script is fetched from the PR's evidence branch `verify/pr-<N>` and run from the reviewed source checkout, so no
report file is handed between passes. The remote is a local bare repository, so the branch is really pushed and
fetched, and the printed command is really run."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from approvals_harness import LOOP, approvals, pull, verdict_on


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_fresh_brief_gives_a_rerun_command_that_runs_the_linked_script_in_the_source_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    monkeypatch.chdir(clone)
    (clone / "source.py").write_text(
        "print('present')\n"
    )  # the source the repro needs, absent on the evidence branch
    repro, log = tmp_path / "r.sh", tmp_path / "l.txt"
    log.write_text("FAILED\n")
    repro.write_text("test -f source.py && echo first\n")
    sha1, [path1, _], _ = approvals.write_evidence(7, 1, "same title", repro, log)
    repro.write_text("test -f source.py && echo second\n")
    sha2, [path2, _], _ = approvals.write_evidence(7, 1, "same title", repro, log)
    assert path1 != path2  # the writer suffixes the second slug
    one = f"**Verifier (codex), pass 1 · F1** (major): same title\n\nsee https://x/blob/{sha1}/{path1}"
    two = f"**Verifier (codex), pass 1 · F2** (major): same title\n\nsee https://x/blob/{sha2}/{path2}"
    done = (
        f"**Verifier (codex), pass 1 · F3** (major): fixed one\n\nsee https://x/blob/{sha1}/{path1}"
    )
    found = pull(
        body="Closes #12.\n", reviews=(verdict_on("c" * 40, heading="Verifier (codex), pass 1"),)
    )
    found["reviewThreads"] = {
        "nodes": [
            {"isResolved": False, "comments": {"nodes": [{"body": one}]}},
            {"isResolved": False, "comments": {"nodes": [{"body": two}]}},
            {"isResolved": True, "comments": {"nodes": [{"body": done}]}},
        ]
    }
    monkeypatch.setattr(approvals, "pull_request", lambda _n: found)
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: "b" * 40)
    monkeypatch.setattr(approvals, "project", lambda: (None, LOOP))
    assert approvals.main(["brief", "7"]) == 0
    out = capsys.readouterr().out
    assert "F3" not in out  # a resolved finding is not open
    commands = [line.split("Rerun: ", 1)[1] for line in out.splitlines() if "Rerun: " in line]
    assert len(commands) == 2
    # each command, run from the source checkout, runs its own finding's script
    for command, word in zip(commands, ("first", "second"), strict=True):
        ran = subprocess.run(
            command, shell=True, cwd=clone, capture_output=True, text=True, check=False
        )
        assert (ran.returncode, ran.stdout.strip()) == (0, word), ran.stderr


def test_a_review_body_finding_keeps_its_link_and_a_missing_blob_fails_the_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A finding outside the diff sits in the review's body with its link under the heading, and a rerun of a blob
    that is not there must fail, not run bash on empty input (#1595)."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    monkeypatch.chdir(clone)
    repro, log = tmp_path / "r.sh", tmp_path / "l.txt"
    repro.write_text("echo actually ran\n")
    log.write_text("ok\n")
    sha, [path, _], _ = approvals.write_evidence(7, 1, "one", repro, log)
    body = (
        "- **Verifier (codex), pass 1 · F1** (major): gap, a file outside the diff\n\n"
        f"  See https://example.test/blob/{sha}/{path}\n"
        "- **Verifier (codex), pass 1 · F2** (minor): other\n"
        "VERDICT: 0 blocker, 1 major, 1 minor\n"
    )
    first, second = approvals.previous_findings({"reviews": {"nodes": [{"body": body}]}}, 1)
    assert "F1" in first and path in first and "F2" not in first and "VERDICT" not in second
    command = approvals.rerun_command(7, first)
    assert command is not None
    ran = subprocess.run(
        command, shell=True, cwd=clone, capture_output=True, text=True, check=False
    )
    assert (ran.returncode, ran.stdout.strip()) == (0, "actually ran"), ran.stderr
    missing = approvals.rerun_command(7, f"https://example.test/blob/{sha}/pass-1/missing/repro.sh")
    assert missing is not None
    gone = subprocess.run(
        missing, shell=True, cwd=clone, capture_output=True, text=True, check=False
    )
    assert gone.returncode != 0
