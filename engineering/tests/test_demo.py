from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "skills" / "demo" / "scripts" / "post_demo.sh"
HEAD = "a" * 40

# A fake gh: answers the PR lookups, lists two earlier demos, and logs every call.
FAKE_GH = """#!/usr/bin/env bash
args="$*"; echo "${args//$'\\n'/ }" >> "$LOG"
case "$*" in
  "pr view --json number --jq .number") echo 7 ;;
  "pr view "*" --json headRefOid --jq .headRefOid") echo "$PR_HEAD" ;;
  "api repos/{owner}/{repo}/issues/"*) printf 'IC_old1\\nIC_old2\\n' ;;
esac
"""


def run(
    tmp_path: Path, *args: str, pr_head: str = HEAD
) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("gh", FAKE_GH), ("git", f"#!/usr/bin/env bash\necho {HEAD}\n")):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    log = tmp_path / "gh.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LOG": str(log),
        "PR_HEAD": pr_head,
    }
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text().splitlines() if log.exists() else []


@pytest.fixture
def video(tmp_path: Path) -> str:
    path = tmp_path / "demo.mp4"
    path.write_bytes(b"\x00video")
    return str(path)


def test_posts_one_demo_and_minimizes_the_earlier_ones(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "the dry run", video)

    assert result.returncode == 0, result.stderr
    comment = next(call for call in calls if call.startswith("pr comment 7"))
    assert "## Demo" in comment and "the dry run, on aaaaaaa." in comment
    assert comment.endswith(f"--attach {video}")
    minimized = [call for call in calls if call.startswith("api graphql")]
    assert [call.split("id=")[-1] for call in minimized] == ["IC_old1", "IC_old2"]
    assert calls.index(comment) > next(i for i, c in enumerate(calls) if c.startswith("api repos/"))


def test_explicit_pr_and_several_videos(tmp_path: Path, video: str) -> None:
    second = tmp_path / "web.mp4"
    second.write_bytes(b"\x00video")

    result, calls = run(tmp_path, "--pr", "12", "cli and web", video, str(second))

    assert result.returncode == 0, result.stderr
    comment = next(call for call in calls if call.startswith("pr comment 12"))
    assert comment.count("--attach") == 2


def test_refuses_a_checkout_that_is_not_the_pr_head(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "the dry run", video, pr_head="b" * 40)

    assert result.returncode == 3
    assert "push or check out the head" in result.stderr
    assert not any(call.startswith("pr comment") for call in calls)


@pytest.mark.parametrize("args", [(), ("caption only",), ("caption", "missing.mp4")])
def test_refuses_bad_arguments(tmp_path: Path, args: tuple[str, ...]) -> None:
    result, calls = run(tmp_path, *args)

    assert result.returncode == 2
    assert calls == []
