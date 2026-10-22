from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "skills" / "demo" / "scripts" / "post_demo.sh"
HEAD = "a" * 40

# A fake gh: answers the lookups, lists two earlier demos of the caller, and logs every call.
# Like gh 2.87.0, `pr comment` has no --attach flag.
FAKE_GH = """#!/usr/bin/env bash
args="$*"; echo "${args//$'\\n'/ }" >> "$LOG"
case "$*" in
  "pr comment "*--attach*) echo "unknown flag: --attach" >&2; exit 1 ;;
  "api repos/{owner}/{repo}/immutable-releases --jq .enabled") echo "$IMMUTABLE"; echo "$IMMUTABLE_ERR" >&2; exit "$IMMUTABLE_RC" ;;
  "release create demo-pr"*) ;;
  "release view demos") exit "$NO_RELEASE" ;;
  "release upload demos "*) [ -s "$4" ] || exit 1 ;;
  "repo view --json url --jq .url") echo https://github.com/o/r ;;
  "pr view --json number --jq .number") echo 7 ;;
  "pr view "*" --json headRefOid --jq .headRefOid") echo "$PR_HEAD" ;;
  "api user --jq .login") echo me ;;
  "api repos/{owner}/{repo}/issues/"*) printf 'IC_old1\\nIC_old2\\n' ;;
esac
"""
FAKE_GIT = f"""#!/usr/bin/env bash
case "$1" in
  rev-parse) echo {HEAD} ;;
  diff) exit "$DIRTY" ;;
esac
"""


def run(
    tmp_path: Path,
    *args: str,
    pr_head: str = HEAD,
    dirty: bool = False,
    no_release: bool = False,
    immutable: str = "false",
    immutable_rc: int = 0,
    immutable_err: str = "",
) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("gh", FAKE_GH), ("git", FAKE_GIT)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    log = tmp_path / "gh.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LOG": str(log),
        "PR_HEAD": pr_head,
        "DIRTY": str(int(dirty)),
        "NO_RELEASE": str(int(no_release)),
        "IMMUTABLE": immutable,
        "IMMUTABLE_RC": str(immutable_rc),
        "IMMUTABLE_ERR": immutable_err,
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


def test_links_release_assets_since_gh_pr_comment_cannot_attach(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "the dry run", video)

    assert result.returncode == 0, result.stderr
    comment = next(call for call in calls if call.startswith("pr comment 7"))
    assert "## Demo" in comment and "the dry run, on aaaaaaa." in comment
    upload = next(call for call in calls if call.startswith("release upload demos"))
    assert upload.endswith("/pr7-aaaaaaa-1.mp4 --clobber")
    link = "https://github.com/o/r/releases/download/demos/pr7-aaaaaaa-1.mp4"
    assert f"[pr7-aaaaaaa-1.mp4]({link})" in comment
    assert calls.index(upload) < calls.index(comment)
    assert not any(call.startswith("release create") for call in calls)
    listing = next(call for call in calls if call.startswith("api repos/"))
    assert '.user.login == "me"' in listing
    minimized = [call for call in calls if call.startswith("api graphql")]
    assert [call.split("id=")[-1] for call in minimized] == ["IC_old1", "IC_old2"]
    assert calls.index(comment) > calls.index(listing)


def test_explicit_pr_and_several_videos(tmp_path: Path, video: str) -> None:
    second = tmp_path / "web.mp4"
    second.write_bytes(b"\x00video")

    result, calls = run(tmp_path, "--pr", "12", "cli and web", video, str(second))

    assert result.returncode == 0, result.stderr
    comment = next(call for call in calls if call.startswith("pr comment 12"))
    assert "pr12-aaaaaaa-1.mp4" in comment and "pr12-aaaaaaa-2.mp4" in comment


def test_creates_the_demos_prerelease_when_missing(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "the dry run", video, no_release=True)

    assert result.returncode == 0, result.stderr
    create = next(call for call in calls if call.startswith("release create demos"))
    assert "--prerelease" in create
    assert calls.index(create) < calls.index(
        next(call for call in calls if call.startswith("release upload"))
    )


def test_immutable_repo_gets_one_prerelease_per_post_with_its_videos(
    tmp_path: Path, video: str
) -> None:
    second = tmp_path / "web.mp4"
    second.write_bytes(b"\x00video")

    result, calls = run(tmp_path, "cli and web", video, str(second), immutable="true")

    assert result.returncode == 0, result.stderr
    create = next(call for call in calls if call.startswith("release create demo-pr7-aaaaaaa-"))
    tag = create.split()[2]
    assert re.fullmatch(r"demo-pr7-aaaaaaa-\d{14}", tag)
    assert "--prerelease" in create and f"--target {HEAD}" in create
    assert "/pr7-aaaaaaa-1.mp4" in create and "/pr7-aaaaaaa-2.mp4" in create
    assert not any(call.startswith(("release upload", "release view")) for call in calls)
    comment = next(call for call in calls if call.startswith("pr comment 7"))
    base = f"https://github.com/o/r/releases/download/{tag}"
    assert f"({base}/pr7-aaaaaaa-1.mp4)" in comment and f"({base}/pr7-aaaaaaa-2.mp4)" in comment
    assert calls.index(create) < calls.index(comment)


@pytest.mark.parametrize(
    ("immutable", "rc", "err"),
    [("false", 0, ""), ("", 1, "gh: Not Found (HTTP 404)")],
)
def test_repo_without_immutable_releases_keeps_the_shared_release(
    tmp_path: Path, video: str, immutable: str, rc: int, err: str
) -> None:
    result, calls = run(
        tmp_path, "the dry run", video, immutable=immutable, immutable_rc=rc, immutable_err=err
    )

    assert result.returncode == 0, result.stderr
    assert any(call.startswith("release upload demos") for call in calls)
    assert not any(call.startswith("release create demo-pr") for call in calls)
    assert "/releases/download/demos/" in next(c for c in calls if c.startswith("pr comment"))


def test_an_unreadable_immutable_setting_stops_before_anything_is_posted(
    tmp_path: Path, video: str
) -> None:
    result, calls = run(
        tmp_path, "the dry run", video, immutable_rc=1, immutable_err="gh: Bad Gateway (HTTP 502)"
    )

    assert result.returncode == 1
    assert "HTTP 502" in result.stderr
    assert not any(call.startswith(("pr comment", "release")) for call in calls)


def test_refuses_a_checkout_that_is_not_the_pr_head(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "the dry run", video, pr_head="b" * 40)

    assert result.returncode == 3
    assert "record from a clean checkout of the head" in result.stderr
    assert not any(call.startswith(("pr comment", "release")) for call in calls)


def test_refuses_uncommitted_changes(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "the dry run", video, dirty=True)

    assert result.returncode == 3
    assert "uncommitted changes" in result.stderr
    assert not any(call.startswith(("pr comment", "release")) for call in calls)


def test_refuses_a_pr_that_is_not_a_number(tmp_path: Path, video: str) -> None:
    result, calls = run(tmp_path, "--pr", "feat/x", "caption", video)

    assert result.returncode == 2
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [(), ("caption only",), ("caption", "missing.mp4")],
)
def test_refuses_bad_arguments(tmp_path: Path, args: tuple[str, ...]) -> None:
    result, calls = run(tmp_path, *args)

    assert result.returncode == 2
    assert calls == []
