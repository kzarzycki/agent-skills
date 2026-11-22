"""`.github/workflows/land-status.yml` (#1816): the `land` status a cloud `land` could not write, posted from its
hand-over record only for a writer's record naming the PR's current head while the PR carries `loop:queued`.

The job's one `run` step is run in bash with a fake `gh` on PATH that answers the permission and PR reads and logs
every status post, so what the workflow would do on GitHub is asserted, not its text.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "land-status.yml"
HEAD = "a" * 40
OTHER = "b" * 40

FAKE_GH = """#!/usr/bin/env bash
case "$*" in
  *collaborators/*/permission*) echo "$PERMISSION" ;;
  *"--jq .head.sha"*) echo "$CURRENT" ;;
  *"--jq [.labels[].name]"*) echo "$QUEUED" ;;
  *"-X POST"*statuses/*) echo "$*" >> "$POSTED" ;;
  *) echo "unexpected gh $*" >&2; exit 2 ;;
esac
"""


def record(head: str = HEAD, first: str = "Queued for Mergify") -> str:
    return (
        f"{first}\nQueued for Mergify at {head[:7]}: the land-status workflow posts the `land` status on it.\n\n"
        f"<details><summary>Details</summary>\n\nHead: {head}\n\n</details>\n"
    )


def run(
    tmp_path: Path,
    body: str,
    permission: str = "write",
    current: str = HEAD,
    queued: str = "true",
) -> tuple[int, str, list[str]]:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    [step] = workflow["jobs"]["post"]["steps"]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "gh").write_text(FAKE_GH)
    (bin_dir / "gh").chmod(0o755)
    posted = tmp_path / "posted.log"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "REPO": "o/r",
        "PR": "7",
        "AUTHOR": "someone",
        "BODY": body,
        "PERMISSION": permission,
        "CURRENT": current,
        "QUEUED": queued,
        "POSTED": str(posted),
    }
    done = subprocess.run(
        ["bash", "-c", step["run"]], env=env, capture_output=True, text=True, check=False
    )
    lines = posted.read_text().splitlines() if posted.exists() else []
    return done.returncode, done.stdout + done.stderr, lines


def test_it_runs_on_a_pr_comment_with_status_write_and_no_checkout() -> None:
    workflow = yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)
    assert workflow["on"] == {"issue_comment": {"types": ["created"]}}
    assert workflow["permissions"] == {"statuses": "write", "pull-requests": "read"}
    job = workflow["jobs"]["post"]
    assert "github.event.issue.pull_request" in job["if"]
    assert all("uses" not in step for step in job["steps"])  # no checkout: no PR code runs
    # the comment's text reaches the script as data, never spliced into it
    assert "${{" not in job["steps"][0]["run"]


def test_a_writers_record_on_the_current_head_posts_land_there(tmp_path: Path) -> None:
    code, out, posted = run(tmp_path, record())
    assert code == 0, out
    assert len(posted) == 1
    assert f"repos/o/r/statuses/{HEAD}" in posted[0]
    assert "context=land" in posted[0] and f"description=Queued for Mergify at {HEAD}" in posted[0]


def test_a_head_that_moved_gets_no_status(tmp_path: Path) -> None:
    code, out, posted = run(tmp_path, record(), current=OTHER)
    assert (code, posted) == (0, []), out
    assert f"head is {OTHER}, not {HEAD}" in out


def test_a_reader_or_a_stranger_gets_no_status(tmp_path: Path) -> None:
    for permission in ("read", "triage", "none"):
        code, out, posted = run(tmp_path, record(), permission=permission)
        assert (code, posted) == (0, []), out


def test_a_pr_without_loop_queued_gets_no_status(tmp_path: Path) -> None:
    code, out, posted = run(tmp_path, record(), queued="false")
    assert (code, posted) == (0, []), out


def test_another_comment_or_a_short_sha_gets_no_status(tmp_path: Path) -> None:
    for body in (
        record(first="Queued for Mergify, maybe"),
        "Queued for Mergify\n\nHead: $(touch pwned)\n",
    ):
        code, out, posted = run(tmp_path, body)
        assert (code, posted) == (0, []), out
    assert not (tmp_path / "pwned").exists()
    # a short sha gets nothing even where the PR's head reads as that same short sha
    code, out, posted = run(tmp_path, record(head=HEAD[:12]), current=HEAD[:12])
    assert (code, posted) == (0, []), out
    assert "names no full head sha" in out
