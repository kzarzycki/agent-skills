"""scripts/mutate.py: a setup failure (the reserved exit code) and a patch that was never built (`--built`) are
inconclusive, never killed or survived, and the run exits 3 (#951, #979)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_mutate import (
    MODULE,
    clean,
    git,
    log,
    mutate,
    own_slot,  # noqa: F401
    patch,
    repo,  # noqa: F401
)

# a "build" that follows the source, one that reuses a stale output, and the test run after each
FRESH = "mkdir -p build && cp calc.py build/lib.txt"
STALE = "mkdir -p build && echo 'a + b' > build/lib.txt"
# the tests run against the build output, not the source
CHECK = "grep -q 'a + b' build/lib.txt"


def commit(repo: Path, message: str) -> None:
    git(repo, "add", ".")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", message)


def ignore_build(repo: Path) -> None:
    (repo / ".gitignore").write_text("tmp/\n__pycache__/\nbuild/\n")
    commit(repo, "ignore build")


def policy(repo: Path, body: str) -> None:
    (repo / "docs" / "agents").mkdir()
    (repo / "docs" / "agents" / "gatekeeper.md").write_text(
        f"# Gatekeeper\n\n## Policy\n\n```yaml\n{body}```\n"
    )
    commit(repo, "policy")


def run_built(
    repo: Path,
    command: str,
    paths: tuple[str, ...],
    *patches: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    flags = [flag for path in paths for flag in ("--built", path)]
    return subprocess.run(
        [
            sys.executable,
            str(MUTATE_PY),
            "--test",
            command,
            "--log",
            str(repo / "tmp/loop/m.log"),
            *flags,
            *map(str, patches),
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=env,
    )


MUTATE_PY = Path(__file__).resolve().parents[1] / "skills/engineering-loop/scripts/mutate.py"


def test_a_test_command_exiting_75_is_inconclusive_not_killed_and_the_run_exits_3(
    repo: Path,
) -> None:
    patched = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, patched, test="if grep -q 'a - b' calc.py; then exit 75; fi")
    assert result.returncode == 3, result.stderr
    assert f"{patched}: exit 75 inconclusive: setup failed, no verdict" in log(repo)
    assert not any("killed" in line or "survived" in line for line in log(repo)[2:])
    assert clean(repo) and (repo / "calc.py").read_text() == MODULE


def test_the_reserved_exit_is_the_policys_and_75_then_counts_as_an_ordinary_failure(
    repo: Path,
) -> None:
    policy(repo, "mutate:\n  inconclusive_exit: 66\n")
    patched = patch(repo, "add.patch", "a + b", "a - b")
    other = patch(repo, "double.patch", "x * 2", "x * 3")
    test = "if grep -q 'a - b' calc.py; then exit 66; fi; if grep -q 'x \\* 3' calc.py; then exit 75; fi"
    result = mutate(repo, patched, other, test=test)
    assert result.returncode == 3, result.stderr
    assert f"{patched}: exit 66 inconclusive: setup failed, no verdict" in log(repo)
    assert f"{other}: exit 75 killed" in log(repo)


@pytest.mark.parametrize("value", ["0", "256", "-1"])
def test_a_reserved_exit_outside_1_to_255_is_refused(repo: Path, value: str) -> None:
    policy(repo, f"mutate:\n  inconclusive_exit: {value}\n")
    patched = patch(repo, "add.patch", "a + b", "a - b")
    result = mutate(repo, patched)
    assert result.returncode == 2 and "inconclusive_exit" in result.stderr
    assert clean(repo)


def test_a_survivor_outranks_an_inconclusive_patch_in_the_exit_code(repo: Path) -> None:
    unbuilt = patch(repo, "add.patch", "a + b", "a - b")
    survivor = patch(repo, "double.patch", "x * 2", "x * 3")
    result = mutate(repo, unbuilt, survivor, test="if grep -q 'a - b' calc.py; then exit 75; fi")
    assert result.returncode == 1
    assert log(repo)[3:5] == [
        f"{unbuilt}: exit 75 inconclusive: setup failed, no verdict",
        f"{survivor}: exit 0 survived",
    ]


def test_a_patch_whose_build_output_is_unchanged_is_not_built_never_survived(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    # the stale build leaves the tests green on the unpatched code: a survivor without the check
    result = run_built(repo, f"{STALE} && {CHECK}", ("build",), patched)
    assert result.returncode == 3, result.stderr
    assert f"{patched}: exit 0 not built: inconclusive" in log(repo)
    assert not any("survived" in line for line in log(repo)[2:])
    assert clean(repo)


def test_a_failing_test_on_an_unchanged_output_is_not_built_either(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    result = run_built(
        repo, f"{STALE}; if grep -q 'a - b' calc.py; then exit 1; fi", ("build",), patched
    )
    assert result.returncode == 3
    assert f"{patched}: exit 1 not built: inconclusive" in log(repo)


def test_a_build_output_that_changes_keeps_todays_verdicts(repo: Path) -> None:
    ignore_build(repo)
    killed = patch(repo, "add.patch", "a + b", "a - b")
    survivor = patch(repo, "double.patch", "x * 2", "x * 3")
    result = run_built(repo, f"{FRESH} && {CHECK}", ("build",), killed, survivor)
    assert result.returncode == 1, result.stderr
    assert log(repo)[3:5] == [f"{killed}: exit 1 killed", f"{survivor}: exit 0 survived"]


def test_a_directory_with_an_unchanged_stub_and_a_changed_library_counts_as_built(
    repo: Path,
) -> None:
    ignore_build(repo)
    patched = patch(repo, "double.patch", "x * 2", "x * 3")
    build = "mkdir -p build/App && echo stub > build/App/main && cp calc.py build/App/lib.debug"
    result = run_built(
        repo, f"{build} && grep -q 'a + b' build/App/lib.debug", ("build/App",), patched
    )
    assert result.returncode == 1, result.stderr
    assert f"{patched}: exit 0 survived" in log(repo)


def test_a_directory_whose_every_file_is_unchanged_is_not_built(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "double.patch", "x * 2", "x * 3")
    build = "mkdir -p build/App && echo stub > build/App/main && echo old > build/App/lib.debug"
    result = run_built(repo, f"{build} && true", ("build/App",), patched)
    assert result.returncode == 3
    assert f"{patched}: exit 0 not built: inconclusive" in log(repo)


def test_a_file_a_build_adds_to_the_directory_counts_as_a_change(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    build = "mkdir -p build/App && echo stub > build/App/main; grep -q 'a - b' calc.py && echo new > build/App/extra"
    result = run_built(repo, f"{build}; grep -q 'a + b' calc.py", ("build/App",), patched)
    assert result.returncode == 0
    assert f"{patched}: exit 1 killed" in log(repo)


def test_built_takes_globs_and_may_repeat_and_one_changed_path_is_enough(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "double.patch", "x * 2", "x * 3")
    build = "mkdir -p build/a build/b && echo same > build/a/x && cp calc.py build/b/y"
    result = run_built(
        repo, f"{build} && grep -q 'a + b' build/b/y", ("build/a", "build/b/*"), patched
    )
    assert result.returncode == 1
    unchanged = run_built(
        repo,
        "mkdir -p build/a build/b && echo same > build/a/x && echo same > build/b/y",
        ("build/a", "build/b/*"),
        patched,
    )
    assert unchanged.returncode == 3


def test_a_path_that_matches_nothing_after_the_head_run_is_refused(repo: Path) -> None:
    patched = patch(repo, "add.patch", "a + b", "a - b")
    result = run_built(repo, "true", ("build",), patched)
    assert result.returncode == 2 and "matches nothing" in result.stderr
    assert clean(repo)


def test_a_build_that_removes_its_output_under_a_patch_is_a_change_and_the_tree_is_restored(
    repo: Path,
) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    build = "mkdir -p build && if grep -q 'a - b' calc.py; then rm -rf build/*; else echo x > build/lib; fi"
    result = run_built(repo, f"{build}; grep -q 'a + b' calc.py", ("build/*",), patched)
    assert result.returncode == 0
    assert f"{patched}: exit 1 killed" in log(repo)
    assert clean(repo) and (repo / "calc.py").read_text() == MODULE


def test_built_runs_a_head_run_even_when_short_seconds_is_0(repo: Path) -> None:
    ignore_build(repo)
    policy(repo, "loop:\n  short_seconds: 0\n")
    patched = patch(repo, "add.patch", "a + b", "a - b")
    result = run_built(repo, f"{STALE} && {CHECK}", ("build",), patched)
    assert result.returncode == 3, result.stderr
    assert log(repo)[2] == "heavy: short_seconds is 0"
    assert "== head ==" in log(repo)


def test_a_reserved_exit_outranks_not_built(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    command = f"{STALE}; if grep -q 'a - b' calc.py; then exit 75; fi"
    result = run_built(repo, command, ("build",), patched)
    assert result.returncode == 3
    assert f"{patched}: exit 75 inconclusive: setup failed, no verdict" in log(repo)


def test_built_runs_a_head_run_under_a_holder_of_the_heavy_slot_too(
    repo: Path, tmp_path: Path
) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    held = tmp_path / "cache" / "engineering-loop" / "gate.1.lock"
    held.parent.mkdir(parents=True)
    env = {
        **os.environ,
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "LOOP_GATE_SLOT_HELD": str(held),
    }
    result = run_built(repo, f"{STALE} && {CHECK}", ("build",), patched, env=env)
    assert result.returncode == 3, result.stderr
    assert log(repo)[2] == "heavy: run under a holder of the heavy slot"
    assert "== head ==" in log(repo)


def test_a_file_renamed_with_the_same_bytes_is_a_change(repo: Path) -> None:
    ignore_build(repo)
    patched = patch(repo, "add.patch", "a + b", "a - b")
    build = (
        "mkdir -p build/App && rm -f build/App/* && if grep -q 'a - b' calc.py;"
        " then echo same > build/App/new; else echo same > build/App/old; fi"
    )
    result = run_built(repo, f"{build}; true", ("build/App",), patched)
    assert result.returncode == 1
    assert f"{patched}: exit 0 survived" in log(repo)
