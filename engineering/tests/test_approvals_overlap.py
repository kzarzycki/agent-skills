"""`overlap` lists the other open PRs into one base that change a file this PR changes, with each side's hunk lines and
whether the two heads merge (#1035); `brief` prints it as a warning on stderr. Each test runs the real git work in real
repos (an origin, and a clone the lead works in); only the one `gh pr list` call is a stand-in."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import LOOP, approvals, pull

BODY = "".join(f"line {n}\n" for n in range(1, 41))


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Repo:
    """origin with `trunk`, and a clone; `open` publishes a PR head as refs/pull/<n>/head and lists it as open."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        origin, self.seed = tmp_path / "origin.git", tmp_path / "seed"
        git(tmp_path, "init", "-q", "--bare", "-b", "trunk", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(self.seed))
        git(self.seed, "checkout", "-q", "-b", "trunk")
        (self.seed / "shared.txt").write_text(BODY)
        git(self.seed, "add", ".")
        git(self.seed, "commit", "-qm", "start")
        git(self.seed, "push", "-q", "origin", "trunk")
        self.start = git(self.seed, "rev-parse", "HEAD")
        self.listed: list[dict[str, Any]] = []
        clone = tmp_path / "clone"
        git(tmp_path, "clone", "-q", str(origin), str(clone))
        monkeypatch.chdir(clone)
        monkeypatch.setattr(approvals, "open_pull_files", lambda _limit: self.listed)
        monkeypatch.setattr(approvals, "default_branch", lambda: "trunk")

    def open(self, number: int, edits: dict[int, str], base: str = "trunk") -> None:
        """PR `number`: the lines `edits` replaces in shared.txt, on the start commit."""
        git(self.seed, "checkout", "-q", "-B", f"pr{number}", self.start)
        lines = BODY.splitlines()
        for n, text in edits.items():
            lines[n - 1] = text
        (self.seed / "shared.txt").write_text("\n".join(lines) + "\n")
        git(self.seed, "commit", "-qam", f"pr {number}")
        head = git(self.seed, "rev-parse", "HEAD")
        git(self.seed, "push", "-q", "origin", f"{head}:refs/pull/{number}/head")
        self.listed.append(
            {"number": number, "baseRefName": base, "headRefOid": head, "files": ["shared.txt"]}
        )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    return Repo(tmp_path, monkeypatch)


def test_pull_requests_changing_the_same_lines_are_listed_as_conflicts(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.open(1, {5: "mine"})
    repo.open(2, {5: "theirs", 6: "theirs too"})
    assert approvals.main(["overlap", "1"]) == 0
    out = capsys.readouterr().out
    assert "PR #2" in out and "conflicts in shared.txt" in out
    assert "shared.txt: PR #1 5; PR #2 5-6" in out
    assert "merges cleanly" not in out


def test_pull_requests_changing_one_file_far_apart_merge_cleanly(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.open(1, {3: "mine"})
    repo.open(2, {30: "theirs"})
    assert approvals.main(["overlap", "1"]) == 0
    out = capsys.readouterr().out
    assert "PR #2" in out and "merges cleanly" in out
    assert "shared.txt: PR #1 3; PR #2 30" in out


def test_a_pull_request_with_no_overlap_prints_nothing(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.open(1, {3: "mine"})
    repo.open(2, {3: "other base"}, base="release")  # same lines, another base
    repo.open(3, {30: "elsewhere"})
    repo.listed[2]["files"] = ["other.txt"]  # a PR on the same base changing another file
    assert approvals.main(["overlap", "1"]) == 0
    assert capsys.readouterr().out == ""


def test_a_fetch_failure_is_an_error_not_a_clean_merge(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.open(1, {3: "mine"})
    repo.open(2, {3: "theirs"})
    repo.listed[1]["number"] = 99  # a head origin has no refs/pull/99/head for
    assert approvals.main(["overlap", "1"]) == 1
    out = capsys.readouterr().out
    assert "cannot fetch" in out and "merges cleanly" not in out


def test_files_lists_the_open_pulls_hunks_with_no_merge_test(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.open(2, {10: "theirs", 11: "theirs"})
    assert approvals.main(["overlap", "--files", "shared.txt"]) == 0
    out = capsys.readouterr().out
    assert "PR #2" in out and "shared.txt: PR #2 10-11" in out
    assert "cleanly" not in out and "conflicts" not in out
    assert approvals.main(["overlap", "--files", "untouched.txt"]) == 0
    assert capsys.readouterr().out == ""


@pytest.fixture
def briefed(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> Repo:
    repo.open(1, {5: "mine"})
    repo.open(2, {5: "theirs"})
    found = pull(body="Closes #12.\n")
    found["headRefOid"], found["baseRefName"] = repo.listed[0]["headRefOid"], "trunk"
    monkeypatch.setattr(approvals, "pull_request", lambda _n: found)
    monkeypatch.setattr(approvals, "merge_base", lambda base, head: repo.start)
    monkeypatch.setattr(approvals, "project", lambda: (None, LOOP))
    monkeypatch.setattr(approvals, "conflicted", lambda _pr, _base, _head: [])
    return repo


def test_brief_warns_on_stderr_and_its_stdout_is_unchanged(
    briefed: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert approvals.main(["brief", "1"]) == 0
    warned = capsys.readouterr()
    assert "PR #2" in warned.err and "conflicts" in warned.err
    assert "overlap" not in warned.out and warned.out.startswith("Review PR #1 as the verifier")
    monkeypatch.setattr(approvals, "overlaps", lambda _pr: [])
    assert approvals.main(["brief", "1"]) == 0
    quiet = capsys.readouterr()
    assert quiet.err == "" and quiet.out == warned.out


def test_an_overlap_failure_is_one_warning_and_the_brief_is_written(
    briefed: Repo, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_limit: int) -> list[dict[str, Any]]:
        raise subprocess.CalledProcessError(1, ["gh"], stderr="rate limited\nmore\n")

    monkeypatch.setattr(approvals, "open_pull_files", broken)
    assert approvals.main(["brief", "1"]) == 0
    seen = capsys.readouterr()
    assert seen.out.startswith("Review PR #1 as the verifier")
    assert seen.err.count("\n") == 1 and "overlap lookup failed" in seen.err


@pytest.mark.parametrize("rest_only", [False, True])
def test_a_pull_request_with_100_files_has_every_file_read(
    monkeypatch: pytest.MonkeyPatch, rest_only: bool
) -> None:
    """`gh pr list` names a PR's first 100 files only, and REST pages 100 at a time: a PR whose 101st file is the one a
    sibling changes is still listed, on the GraphQL path and on the REST one a cloud proxy forces."""
    github = approvals.github
    many = [f"f{n}.py" for n in range(150)]
    listed = [
        {
            "number": 7,
            "baseRefName": "trunk",
            "headRefOid": "a" * 40,
            "files": [{"path": p} for p in many[:100]],
        },
        {"number": 8, "baseRefName": "trunk", "headRefOid": "b" * 40, "files": [{"path": "g.py"}]},
    ]
    pulls = [
        {"number": p["number"], "base": {"ref": "trunk"}, "head": {"sha": p["headRefOid"]}}
        for p in listed
    ]
    files = {7: many, 8: ["g.py"]}

    def pages(path: str, items: str = ".[]") -> list[Any]:
        if path.startswith("pulls?"):
            return pulls
        return files[int(path.split("/")[1])]

    monkeypatch.setattr(github, "gh", lambda *_args: json.dumps(listed))
    monkeypatch.setattr(github, "rest_pages", pages)
    monkeypatch.setattr(github, "_rest_only", rest_only)
    found = {p["number"]: p["files"] for p in github.open_pull_files(1000)}
    assert found == {7: many, 8: ["g.py"]}
