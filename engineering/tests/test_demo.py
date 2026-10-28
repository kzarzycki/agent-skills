from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "skills" / "demo" / "scripts" / "demo.sh"
HEAD = "a" * 40

# A fake gh: answers the lookups, lists two earlier demos of the caller, and logs every call.
FAKE_GH = """#!/usr/bin/env bash
args="$*"; echo "gh ${args//$'\\n'/ }" >> "$LOG"
case "$*" in
  "--version") echo "gh version $GH_VERSION (2026-10-26)" ;;
  "pr view --json number --jq .number") echo 7 ;;
  "pr view "*" --json headRefOid --jq .headRefOid") echo "$PR_HEAD" ;;
  "api user --jq .login") echo me ;;
  "api repos/{owner}/{repo}/issues/"*) printf 'IC_old1\\nIC_old2\\n' ;;
  "pr comment "*)
    for arg in "$@"; do [ -z "$next" ] || { [ -s "$arg" ] || exit 1; next=""; }; if [ "$arg" = --attach ]; then next=1; fi; done ;;
esac
"""
FAKE_GIT = f"""#!/usr/bin/env bash
echo "git $*" >> "$LOG"
case "$1" in
  rev-parse) echo {HEAD} ;;
  status) printf '%s' "$STATUS" ;;
  config) exit 1 ;;
esac
"""
# vhs and ffmpeg write the output they are given and log the call; the output is the last argument.
FAKE_RECORDER = """#!/usr/bin/env bash
echo "$(basename "$0") $*" >> "$LOG"
for last; do :; done
printf 'video' > "$last"
"""


def run(
    tmp_path: Path,
    *args: str,
    pr_head: str = HEAD,
    status: str = "",
    gh_version: str = "2.103.3",
    ttyd: bool = True,
    command: tuple[str, ...] | None = None,
) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tools = {"gh": FAKE_GH, "git": FAKE_GIT, "vhs": FAKE_RECORDER, "ffmpeg": FAKE_RECORDER}
    if ttyd:
        tools["ttyd"] = "#!/bin/sh\n"
    for name, body in tools.items():
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(0o755)
    log = tmp_path / "calls.log"
    env = {
        **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "LOG": str(log),
        "PR_HEAD": pr_head,
        "STATUS": status,
        "GH_VERSION": gh_version,
    }
    if command:
        env["PATH"] += f":{Path(shutil.which('mise') or 'mise').parent}"
        env["MISE_TRUSTED_CONFIG_PATHS"] = str(tmp_path)
    result = subprocess.run(
        list(command or ("bash", str(SCRIPT), *args)),
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, log.read_text().splitlines() if log.exists() else []


def recording(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(b"\x00recording")
    return str(path)


def test_one_comment_attaches_every_recording_and_minimizes_only_my_earlier_demos(
    tmp_path: Path,
) -> None:
    tape, webm, mp4 = (recording(tmp_path, n) for n in ("cli.tape", "web.webm", "app.mp4"))

    result, calls = run(tmp_path, tape, webm, mp4)

    assert result.returncode == 0, result.stderr
    comment = next(call for call in calls if call.startswith("gh pr comment 7"))
    assert "## Demo" in comment and "cli.tape, web.webm, app.mp4, on aaaaaaa." in comment
    assert comment.count("--attach") == 3
    for i in (1, 2, 3):
        assert f"/pr7-aaaaaaa-{i}.mp4" in comment
    assert next(c for c in calls if c.startswith("vhs ")).startswith(f"vhs {tape} -o ")
    assert "-c:v libx264 -pix_fmt yuv420p" in next(c for c in calls if c.startswith("ffmpeg "))
    listing = next(call for call in calls if call.startswith("gh api repos/"))
    assert '.user.login == "me"' in listing
    minimized = [call for call in calls if call.startswith("gh api graphql")]
    assert [call.split("id=")[-1] for call in minimized] == ["IC_old1", "IC_old2"]
    assert calls.index(listing) < calls.index(comment) < calls.index(minimized[0])
    assert not any(call.startswith("gh release") for call in calls)


def test_explicit_pr_and_caption(tmp_path: Path) -> None:
    result, calls = run(
        tmp_path, "--pr", "12", "--caption", "the dry run", recording(tmp_path, "a.mp4")
    )

    assert result.returncode == 0, result.stderr
    comment = next(call for call in calls if call.startswith("gh pr comment 12"))
    assert "the dry run, on aaaaaaa." in comment and "/pr12-aaaaaaa-1.mp4" in comment


RECORDED = ("vhs ", "ffmpeg ", "gh pr comment")


@pytest.mark.parametrize(
    ("setup", "code", "message"),
    [
        ({"pr_head": "b" * 40}, 3, "record from a clean checkout of the head"),
        ({"status": " M tool.py\n"}, 3, "uncommitted or untracked"),
        ({"status": "?? helper.py\n"}, 3, "uncommitted or untracked"),
        ({"gh_version": "2.87.0"}, 1, "upgrade gh to 2.99.0 or later, else stop and report"),
        ({"ttyd": False}, 1, "needs ttyd"),
    ],
)
def test_every_refusal_comes_before_anything_records(
    tmp_path: Path, setup: dict, code: int, message: str
) -> None:
    result, calls = run(
        tmp_path, recording(tmp_path, "cli.tape"), recording(tmp_path, "web.webm"), **setup
    )

    assert result.returncode == code
    assert message in result.stderr
    assert not any(call.startswith(RECORDED) for call in calls)


def test_untracked_files_are_read_whatever_show_untracked_files_says(tmp_path: Path) -> None:
    result, calls = run(tmp_path, recording(tmp_path, "a.mp4"), status="?? helper.py\n")

    assert result.returncode == 3
    assert any(call == "git status --porcelain --untracked-files=all" for call in calls)


@pytest.mark.parametrize(
    "args",
    [(), ("missing.mp4",), ("--pr", "feat/x", "a.mp4"), ("--caption",), ("notes.txt",)],
)
def test_refuses_bad_arguments_before_any_call(tmp_path: Path, args: tuple[str, ...]) -> None:
    recording(tmp_path, "a.mp4")
    recording(tmp_path, "notes.txt")

    result, calls = run(tmp_path, *args)

    assert result.returncode == 2
    assert calls == []


@pytest.mark.skipif(shutil.which("mise") is None, reason="needs mise")
def test_a_mise_task_passes_a_path_with_a_space_as_one_argument(tmp_path: Path) -> None:
    (tmp_path / "mise.toml").write_text(
        f"""[tasks."pr:demo"]
usage = 'arg "<recording>" var=#true'
run = 'eval "set -- $usage_recording"; bash {SCRIPT} "$@"'
"""
    )
    spaced = recording(tmp_path, "my demo.mp4")

    result, calls = run(tmp_path, command=("mise", "run", "pr:demo", spaced))

    assert result.returncode == 0, result.stderr
    assert "my demo.mp4, on aaaaaaa." in next(c for c in calls if c.startswith("gh pr comment"))
