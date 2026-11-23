"""gh-quota: the logging shim leaves gh's output and exit code alone and logs one masked line per call; the report
ranks callers; rate counts spend across a reset."""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "gh-quota" / "scripts"
spec = importlib.util.spec_from_file_location("gh_quota", SCRIPTS / "gh_quota.py")
assert spec and spec.loader
gq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gq)

FAKE_GH = """#!/bin/sh
printf 'out:%s\\n' "$*"
printf 'err:%s\\n' "$*" >&2
read -r line && printf 'stdin:%s\\n' "$line"
exit 3
"""


@pytest.fixture
def setup(tmp_path: Path) -> tuple[dict[str, str], Path]:
    real = tmp_path / "real"
    real.mkdir()
    (real / "gh").write_text(FAKE_GH)
    (real / "gh").chmod(0o755)
    shims = tmp_path / "shims"
    log = tmp_path / "calls.log"
    env = {
        "PATH": f"{shims}:{real}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GH_QUOTA_LOG": str(log),
        "OMNIGENT_SESSION_ID": "s1",
        "SECRET_ENV": "never-logged",
    }
    assert gq.install(shims, env["PATH"]) == 0
    return env, log


def test_the_shim_keeps_output_exit_code_and_stdin(setup: tuple[dict[str, str], Path]) -> None:
    env, log = setup
    done = subprocess.run(
        ["gh", "api", "repos/o/r/pulls/12"],
        input="hello\n",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (done.returncode, done.stdout, done.stderr) == (
        3,
        "out:api repos/o/r/pulls/12\nstdin:hello\n",
        "err:api repos/o/r/pulls/12\n",
    )
    [line] = log.read_text().splitlines()
    when, host, session, cwd, parent, args = line.split("\t")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", when)
    assert (session, args) == ("s1", "api repos/o/r/pulls/12")
    assert host and cwd and parent


def test_the_shim_masks_tokens_and_logs_no_env(setup: tuple[dict[str, str], Path]) -> None:
    env, log = setup
    token = "ghp_" + "A1b2" * 9
    subprocess.run(
        [
            "gh",
            "api",
            "user",
            "-H",
            f"Authorization: token {token}",
            "-f",
            f"note=github_pat_{'x' * 30}",
        ],
        input="",
        env=env,
        capture_output=True,
        check=False,
    )
    text = log.read_text()
    assert token not in text and "github_pat_x" not in text and "never-logged" not in text
    assert "Authorization: ***" in text and "github_pat_***" in text and "A1b2" not in text


def test_a_log_it_cannot_write_never_stops_the_call(
    setup: tuple[dict[str, str], Path], tmp_path: Path
) -> None:
    env, _ = setup
    blocked = tmp_path / "file"
    blocked.write_text("")
    env = {**env, "GH_QUOTA_LOG": str(blocked / "calls.log")}
    done = subprocess.run(
        ["gh", "status"], input="", env=env, capture_output=True, text=True, check=False
    )
    assert (done.returncode, done.stdout) == (3, "out:status\n")


def test_install_refuses_a_real_gh_and_a_folder_behind_it(
    tmp_path: Path, setup: tuple[dict[str, str], Path]
) -> None:
    env, _ = setup
    real = tmp_path / "real"
    assert gq.install(real, env["PATH"]) == 1
    assert "gh-quota's logging shim" not in (real / "gh").read_text()
    behind = tmp_path / "behind"
    assert gq.install(behind, f"{real}:{behind}") == 1
    assert gq.install(tmp_path / "shims", env["PATH"]) == 0  # again over its own copy


def test_report_ranks_callers_and_folds_numbers(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    stamp = lambda minutes: (now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        f"{stamp(1)}\th1\ts1\t/w\tpython3 /a/b/approvals.py land --wait\tapi repos/o/r/pulls/{n}/reviews"
        for n in (1, 2, 3)
    ]
    lines.append(f"{stamp(2)}\th2\t-\t/w\tpython3 /c/omnigent_agent.py supervise\tpr view 5")
    lines.append(f"{stamp(90)}\th3\t-\t/w\told caller\tapi x")  # outside the window
    log = tmp_path / "calls.log"
    log.write_text("\n".join(lines) + "\nnot a line\n")
    counted = gq.tally([log], now - timedelta(minutes=10))
    assert (
        counted[("h1", "s1", "python3 approvals.py land --wait", "api repos/o/r/pulls/N/reviews")]
        == 3
    )
    text = gq.report(counted, 10, 20)
    assert text.splitlines()[0] == "4 gh calls in the last 10 min (0.4/min), by caller:"
    assert text.index("approvals.py land --wait") < text.index("omnigent_agent.py supervise")
    assert "old caller" not in text
    posted = tmp_path / "counts.tsv"
    posted.write_text("".join(f"{n}\t{h}\t{s}\t{p}\t{c}\n" for (h, s, p, c), n in counted.items()))
    assert gq.read_counts([posted]) == counted


def test_spent_counts_across_a_reset() -> None:
    assert gq.spent([(0, 100, 1), (60, 250, 1), (120, 40, 2), (180, 90, 2)]) == 150 + 40 + 50


def test_shim_runs_under_plain_sh() -> None:
    assert subprocess.run(["sh", "-n", str(SCRIPTS / "gh")], check=False).returncode == 0
    assert os.access(SCRIPTS / "gh", os.X_OK)
