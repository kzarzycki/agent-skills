"""The evidence writer (#1595): a finding's repro and log go on the orphan branch `verify/pr-<N>`; a log over 50 MB is
gzipped, one still over it goes to the PR's draft release, one over the asset limit is refused with its size and the
limit, its repro still stored. The limits are shrunk so the files stay small; `gh` is stubbed."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from approvals_harness import approvals


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def clone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    origin, work = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    monkeypatch.chdir(work)
    monkeypatch.setattr(approvals, "BRANCH_LIMIT", 10)
    monkeypatch.setattr(approvals, "ASSET_LIMIT", 1000)
    return tmp_path / "origin.git"


def files(tmp_path: Path) -> tuple[Path, Path]:
    repro, log = tmp_path / "r.sh", tmp_path / "l.txt"
    repro.write_text("echo go\n")
    log.write_bytes(os.urandom(200))  # incompressible: gzip leaves it over the 10-byte branch limit
    return repro, log


def test_a_log_still_over_the_limit_after_gzip_goes_to_the_draft_release(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []

    def gh(*args: str, data: str | None = None) -> str:
        calls.append(args)
        if (
            "--jq" in args
            and args[-1]
            == '[.[] | select(.tag_name == "verify/pr-7-evidence")][0].upload_url // ""'
        ):
            return ""
        if args[-1] == ".upload_url":
            return "https://uploads.example/releases/1/assets{?name,label}"
        return "https://example/download/log.txt.gz"

    monkeypatch.setattr(approvals.github, "gh", gh)
    repro, log = files(tmp_path)
    sha, written, asset = approvals.write_evidence(7, 2, "Slow probe", repro, log)
    assert written == ["pass-2/slow-probe/repro.sh"]  # the log is not on the branch
    assert asset == "https://example/download/log.txt.gz"
    create = next(c for c in calls if "tag_name=verify/pr-7-evidence" in c)
    assert "draft=true" in create
    assert any("assets" in a and "name=log.txt.gz" in a for c in calls for a in c)
    assert git(clone, "show", "verify/pr-7:pass-2/slow-probe/repro.sh") == "echo go"
    assert git(clone, "rev-parse", "verify/pr-7") == sha


def test_a_log_over_two_gigabytes_is_refused_with_its_size_and_the_limit_but_the_repro_is_kept(
    clone: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(approvals, "ASSET_LIMIT", 50)
    monkeypatch.setattr(approvals.github, "gh", lambda *a, **k: pytest.fail("no release call"))
    repro, log = files(tmp_path)
    with pytest.raises(approvals.Refused) as raised:
        approvals.write_evidence(7, 1, "big", repro, log)
    message = str(raised.value)
    assert "200 bytes" in message and "50-byte limit" in message
    assert git(clone, "show", "verify/pr-7:pass-1/big/repro.sh") == "echo go"
    assert "log" not in git(clone, "ls-tree", "-r", "--name-only", "verify/pr-7")


def test_a_second_finding_is_added_on_top_of_the_branch_that_origin_already_holds(
    clone: Path, tmp_path: Path
) -> None:
    repro, log = tmp_path / "r.sh", tmp_path / "l.txt"
    repro.write_text("echo go\n")
    log.write_text("ok\n")
    approvals.write_evidence(7, 1, "one", repro, log)
    approvals.write_evidence(7, 1, "two", repro, log)
    names = git(clone, "ls-tree", "-r", "--name-only", "verify/pr-7").splitlines()
    assert "pass-1/one/log.txt" in names and "pass-1/two/log.txt" in names
