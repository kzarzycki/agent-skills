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


def test_spent_skips_a_sample_from_another_bucket() -> None:
    # a first reply from another token's window (10 used) is not 4061 calls spent in a minute
    assert gq.spent([(0, 10, 5), (60, 4071, 9), (120, 4117, 9)]) == 46


def test_shim_runs_under_plain_sh() -> None:
    assert subprocess.run(["sh", "-n", str(SCRIPTS / "gh")], check=False).returncode == 0
    assert os.access(SCRIPTS / "gh", os.X_OK)


def logged_args(log: Path) -> list[str]:
    return [line.split("\t")[5] for line in log.read_text().splitlines()]


def test_the_shim_passes_each_argument_whole(setup: tuple[dict[str, str], Path]) -> None:
    env, _ = setup
    done = subprocess.run(
        ["gh", "api", "-f", "body=two words", "*"],
        input="",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.stdout.splitlines()[0] == "out:api -f body=two words *"
    # a fake gh that counts its arguments shows "a b" stayed one
    real = Path(env["PATH"].split(":")[1]) / "gh"
    real.write_text('#!/bin/sh\necho "$#"\n')
    assert (
        subprocess.run(
            ["gh", "a b", "c"], env=env, capture_output=True, text=True, check=False
        ).stdout
        == "2\n"
    )


@pytest.mark.parametrize(
    ("args", "hidden"),
    [
        (["api", "user", "-H", "AUTHORIZATION: bearer abc123secret"], "abc123secret"),
        (["api", "x", "-f", "token=" + "0123456789abcdef" * 2 + "01234567"], "0123456789abcdef"),
        (["secret", "set", "NAME", "--body", "s3cr3t-value"], "s3cr3t-value"),
        (["secret", "set", "NAME", "--body=s3cr3t-value"], "s3cr3t-value"),
        (["variable", "set", "NAME", "-b", "s3cr3t-value"], "s3cr3t-value"),
        (["api", "x", "-F", "client_secret=s3cr3t-value"], "s3cr3t-value"),
    ],
)
def test_the_shim_masks_secret_values(
    setup: tuple[dict[str, str], Path], args: list[str], hidden: str
) -> None:
    env, log = setup
    subprocess.run(["gh", *args], input="", env=env, capture_output=True, check=False)
    assert hidden not in log.read_text() and "***" in log.read_text()


def test_the_shim_logs_both_session_ids_and_cuts_long_arguments(
    setup: tuple[dict[str, str], Path],
) -> None:
    env, log = setup
    env = {**env, "OMNIGENT_RUNNER_PRIMARY_SESSION_ID": "p1"}
    subprocess.run(
        ["gh", "api", "-f", "body=" + "x" * 1000],
        input="",
        env=env,
        capture_output=True,
        check=False,
    )
    line = log.read_text().splitlines()[-1].split("\t")
    assert line[2] == "s1/p1" and len(line[5]) == 400


def test_a_shell_parent_names_the_command_that_ran_it(setup: tuple[dict[str, str], Path]) -> None:
    env, log = setup
    subprocess.run(
        ["python3", "-c", "import subprocess; subprocess.run(['sh', '-c', 'gh x; true'])"],
        env=env,
        check=False,
    )
    parent = log.read_text().splitlines()[-1].split("\t")[4]
    assert parent.startswith("python3 -c import subprocess") and " > sh -c gh x; true" in parent


def test_a_second_copy_is_skipped_and_no_real_gh_exits_127(
    setup: tuple[dict[str, str], Path], tmp_path: Path
) -> None:
    env, log = setup
    other = tmp_path / "other"
    other.mkdir()
    (other / "gh").write_bytes((SCRIPTS / "gh").read_bytes())
    (other / "gh").chmod(0o755)
    env = {**env, "PATH": f"{tmp_path / 'shims'}:{other}:{env['PATH']}"}
    done = subprocess.run(
        ["gh", "status"], input="", env=env, capture_output=True, text=True, check=False, timeout=10
    )
    assert (done.returncode, done.stdout) == (3, "out:status\n") and len(
        log.read_text().splitlines()
    ) == 1
    alone = {**env, "PATH": f"{tmp_path / 'shims'}:{other}:/usr/bin:/bin"}
    done = subprocess.run(
        ["gh", "status"], env=alone, capture_output=True, text=True, check=False, timeout=10
    )
    assert done.returncode == 127 and "no real gh" in done.stderr


def test_command_keeps_the_route_past_flags() -> None:
    assert (
        gq.command("api -X POST repos/o/r/pulls/12/reviews -f body=x")
        == "api POST repos/o/r/pulls/N/reviews"
    )
    assert (
        gq.command("api -H Accept:x repos/o/r/commits/abcdef1234567/status")
        == "api repos/o/r/commits/N/status"
    )
    assert gq.command("api --method=PATCH repos/o/r/issues/5") == "api PATCH repos/o/r/issues/N"
    assert gq.command("pr view 5 --json x") == "pr view"


def test_the_report_reads_a_flag_value_with_a_space(setup: tuple[dict[str, str], Path]) -> None:
    env, log = setup
    subprocess.run(
        ["gh", "api", "-H", "Accept: x", "repos/o/r/rulesets/7"],
        input="",
        env=env,
        capture_output=True,
        check=False,
    )
    assert gq.command(logged_args(log)[-1]) == "api repos/o/r/rulesets/N"


@pytest.mark.parametrize("flag", ["-bs3cr3t-value", "-b=s3cr3t-value"])
def test_a_joined_secret_body_is_masked(setup: tuple[dict[str, str], Path], flag: str) -> None:
    env, log = setup
    subprocess.run(
        ["gh", "secret", "set", "NAME", flag], input="", env=env, capture_output=True, check=False
    )
    assert "s3cr3t-value" not in log.read_text()


def test_a_token_in_the_parent_command_is_masked(setup: tuple[dict[str, str], Path]) -> None:
    env, log = setup
    hexed = "0123456789abcdef" * 2 + "01234567"
    subprocess.run(
        ["sh", "-c", f"GH_TOKEN={hexed} gh x; X={hexed}; true"],
        env=env,
        check=False,
        capture_output=True,
    )
    assert hexed not in log.read_text()


def test_the_host_falls_back_to_uname(setup: tuple[dict[str, str], Path], tmp_path: Path) -> None:
    env, log = setup
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    (fakes / "hostname").write_text("#!/bin/sh\nexit 1\n")
    (fakes / "uname").write_text("#!/bin/sh\necho fallback.example\n")
    for fake in fakes.iterdir():
        fake.chmod(0o755)
    env = {**env, "PATH": f"{tmp_path / 'shims'}:{fakes}:{env['PATH']}"}
    subprocess.run(["gh", "x"], input="", env=env, capture_output=True, check=False)
    assert log.read_text().splitlines()[-1].split("\t")[1] == "fallback"
