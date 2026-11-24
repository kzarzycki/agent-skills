"""approvals.py queue-select (R6, #2279): a consumer's merge-queue job runs the verb on the batch it checked out and
runs each line it prints. Driven as that job drives it, a subprocess in a clone of a bare origin, with no forge."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

APPROVALS = (
    Path(__file__).resolve().parents[1] / "skills" / "gatekeeper" / "scripts" / "approvals.py"
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A project on main whose loop.md is set by `loop(text)`, and `batch(*prs)`: each PR (its number and the file it
    adds) branches off main and merges onto a batch branch the way a queue builds one (`Merge of PR <n>`), leaving
    HEAD on the batch. `run(*args)` runs approvals.py there; `record(pr)` records the PR's affected tests on its head."""
    origin, repo = tmp_path / "origin.git", tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.email", "loop@example.com")
    git(repo, "config", "user.name", "loop")
    git(repo, "checkout", "-q", "-b", "main")
    (repo / "docs" / "agents").mkdir(parents=True)
    for var in ("GATE_BASE", "FULL_GATE", "GATE_SLOTS"):
        monkeypatch.delenv(var, raising=False)
    env = {**os.environ, "GATEKEEPER_POLICY_FROM_WORKING_TREE": "1", "GATE_SLOTS": "off"}
    heads: dict[int, str] = {}

    def commit(path: str, text: str, message: str) -> None:
        (repo / path).write_text(text)
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", message)

    def loop(text: str, policy: str = 'loop:\n  gate: "true"\n') -> str:
        (repo / "docs" / "agents" / "gatekeeper.md").write_text(
            f"# Gatekeeper\n\n## Policy\n\n```yaml\n{policy}```\n"
        )
        commit("docs/agents/loop.md", text, "loop")
        git(repo, "push", "-q", "-u", "origin", "main")
        return git(repo, "rev-parse", "HEAD")

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(APPROVALS), *args],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def build(*prs: int) -> None:
        for pr in prs:
            git(repo, "checkout", "-q", "-b", f"pr{pr}", "main")
            commit(f"f{pr}.py", f"x = {pr}\n", f"pr {pr}")
            git(repo, "push", "-q", "origin", f"pr{pr}")
            heads[pr] = git(repo, "rev-parse", "HEAD")
        git(repo, "checkout", "-q", "-b", "batch", "main")
        for pr in prs:
            git(repo, "merge", "-q", "--no-ff", "-m", f"Merge of PR {pr}", f"pr{pr}")

    def record(pr: int) -> None:
        here = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        git(repo, "checkout", "-q", f"pr{pr}")
        done = run("affected-tests", "--record", "--base", "origin/main")
        git(repo, "checkout", "-q", here)
        assert done.returncode == 0, done.stdout + done.stderr

    return {
        "repo": repo,
        "loop": loop,
        "build": build,
        "run": run,
        "record": record,
        "heads": heads,
    }


def run_lines(repo: Path, stdout: str) -> list[int]:
    """What the consumer's job does with the verb's output: each line through `sh -c`, every one to pass."""
    return [
        subprocess.run(["sh", "-c", line], cwd=repo, check=False).returncode
        for line in stdout.splitlines()
    ]


def test_a_batch_whose_prs_all_have_a_record_runs_only_the_unkeyed_checks(batch) -> None:
    batch["loop"](
        "# Loop\n\nAffected tests: true\n",
        "loop:\n  gate: echo live\nselect:\n  unkeyed: [echo live]\n",
    )
    batch["build"](1, 2)
    batch["record"](1)
    batch["record"](2)
    done = batch["run"]("queue-select", "main")
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines() == ["echo live"], done.stderr
    assert done.stderr.count("record found") == 2, done.stderr
    assert run_lines(batch["repo"], done.stdout) == [0]


def test_a_pr_with_no_record_runs_its_own_affected_tests_from_its_branch_point(batch) -> None:
    point = batch["loop"]("# Loop\n\nAffected tests: true\n")
    batch["build"](1, 2)
    batch["record"](1)
    done = batch["run"]("queue-select", "main")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert len(lines) == 1 and lines[0].endswith(f"affected-tests --base {point}"), done.stdout
    assert "PR #2: no record, so its own affected tests run" in done.stderr
    assert run_lines(batch["repo"], done.stdout) == [0]


def test_a_batch_with_nothing_to_run_and_a_pr_without_a_record_is_refused(batch) -> None:
    batch["loop"]("# Loop\n")
    batch["build"](1)
    done = batch["run"]("queue-select", "main")
    assert done.returncode == 1, done.stdout
    assert done.stdout == ""
    assert "queue-select: refused: nothing to run, and #1 has no record" in done.stderr
