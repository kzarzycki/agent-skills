"""The incubating nightly workflow: it reports, never blocks, runs only for an open epic, and runs only `mise run <task>` (#1288)."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

FILE = Path(__file__).resolve().parents[1] / ".github/workflows/incubating-nightly.yml"


@pytest.fixture(scope="module")
def flow() -> dict[str, Any]:
    return yaml.safe_load(FILE.read_text())


def test_it_runs_on_a_schedule_and_by_hand_and_never_on_a_pull_request(
    flow: dict[str, Any],
) -> None:
    triggers = flow[True]  # YAML 1.1 reads the key `on` as true
    assert set(triggers) == {"schedule", "workflow_dispatch"}


def test_it_may_only_comment_and_read(flow: dict[str, Any]) -> None:
    assert flow["permissions"] == {"contents": "read", "issues": "write"}


def test_every_step_after_the_listing_waits_for_an_epic(flow: dict[str, Any]) -> None:
    steps = flow["jobs"]["nightly"]["steps"]
    assert steps[0]["id"] == "epics"
    assert all("steps.epics.outputs.numbers != ''" in step["if"] for step in steps[1:])


def test_a_stale_reminder_is_counted_by_the_bot_only() -> None:
    text = FILE.read_text()
    assert "github-actions[bot]" in text and 'startswith("Still incubating")' in text
    assert "| min //" in text  # the first label event: a label put back doesn't restart the clock


def test_the_body_parser_takes_only_a_flag_name_and_a_mise_task() -> None:
    """The shell loop of the workflow, run on bodies: an injected command is not a `Nightly:` line."""
    text = FILE.read_text()
    start = text.index('            flag="" cmd=""')
    end = text.index('            done <<< "$body"') + len('            done <<< "$body"')
    parser = "\n".join(line[12:] for line in text[start:end].splitlines())
    script = f"tick=$(printf '\\x60')\n{parser}\necho \"[$flag][$cmd]\"\n"

    def run(body: str) -> str:
        return subprocess.run(
            ["bash", "-c", script],
            input="",
            env={"body": body, "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    ok = run("Flag: `FEAT_X`\nNightly: `mise run nightly:feat`")
    assert ok == "[FEAT_X][mise run nightly:feat]"
    assert run("Nightly: mise run a:b; rm -rf /\nFlag: X1") == "[X1][]"
    assert run("Flag: none") == "[none][]"


def _step(flow: dict[str, Any]) -> str:
    return next(
        s["run"]
        for s in flow["jobs"]["nightly"]["steps"]
        if s.get("name", "").startswith("Report each epic")
    )


GH = r"""#!/bin/bash
# a stand-in for `gh api`: one epic, its body, label date and bot comment dates come from the environment
case "$*" in
  *"-f body="*) printf '%s\n' "$*" >> "$POSTS" ;;
  */events*) printf '%s\n' "$SINCE" ;;
  */comments*) printf '%s\n' "$SAID" ;;
  *) printf '%s\n' "$BODY" ;;
esac
"""


def _night(
    flow: dict[str, Any],
    tmp_path: Path,
    since: str,
    said: str = "",
    body: str = "",
    mise: str = "exit 0",
) -> tuple[str, str, int]:
    gnu = shutil.which("gdate") or shutil.which("date")
    if subprocess.run([gnu, "-u", "-d", "@0"], capture_output=True, check=False).returncode:
        pytest.skip("needs GNU date")
    for name, text in {
        "gh": GH,
        "mise": f"#!/bin/bash\n{mise}\n",
        "uv": "#!/bin/bash\nexit 0\n",
        "date": f'#!/bin/bash\nexec {gnu} "$@"\n',
    }.items():
        (tmp_path / name).write_text(text)
        (tmp_path / name).chmod(0o755)
    summary, posts = tmp_path / "summary", tmp_path / "posts"
    summary.touch(), posts.touch()
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "NUMBERS": "7",
        "STALE_DAYS": "30",
        "REPO": "o/r",
        "RUN": "RUN-URL",
        "GITHUB_STEP_SUMMARY": str(summary),
        "POSTS": str(posts),
        "SINCE": since,
        "SAID": said,
        "BODY": body,
    }
    done = subprocess.run(
        ["bash", "-c", _step(flow)], env=env, capture_output=True, text=True, check=False
    )
    return summary.read_text(), posts.read_text(), done.returncode


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_an_old_epic_is_listed_with_its_age_and_gets_a_reminder(
    flow: dict[str, Any], tmp_path: Path
) -> None:
    listing, posts, code = _night(flow, tmp_path, since=_ago(45))
    assert "#7: incubating 45 days, flag unset, nightly none" in listing
    assert "Still incubating" in posts and "45 days" in posts
    assert code == 0


def test_a_young_epic_or_a_recent_reminder_gets_none(flow: dict[str, Any], tmp_path: Path) -> None:
    assert _night(flow, tmp_path, since=_ago(5))[1] == ""
    assert _night(flow, tmp_path, since=_ago(90), said=_ago(3))[1] == ""


def test_an_epic_with_no_label_event_is_listed_and_left_alone(
    flow: dict[str, Any], tmp_path: Path
) -> None:
    listing, posts, _ = _night(flow, tmp_path, since="")
    assert "#7: incubating ? days" in listing and posts == ""


def test_a_failing_nightly_is_commented_and_fails_the_run(
    flow: dict[str, Any], tmp_path: Path
) -> None:
    body = "Flag: `FEAT_X`\nNightly: `mise run nightly:feat`"
    listing, posts, code = _night(
        flow, tmp_path, since=_ago(1), body=body, mise='[ "$1" = run ] && exit 1; exit 0'
    )
    assert "flag FEAT_X, nightly mise run nightly:feat" in listing
    assert "failed with `FEAT_X=1`" in posts and "RUN-URL" in posts
    assert code == 1


def test_a_broken_install_does_not_hide_the_listing(flow: dict[str, Any], tmp_path: Path) -> None:
    body = "Flag: FEAT_X\nNightly: mise run nightly:feat"
    listing, _, code = _night(
        flow, tmp_path, since=_ago(1), body=body, mise='[ "$1" = install ] && exit 1; exit 0'
    )
    assert "#7: incubating 1 days" in listing and code == 1
