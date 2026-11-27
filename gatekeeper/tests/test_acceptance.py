"""scripts/acceptance.py: the fallback runner of a spec's acceptance checks, and the lines that tell
the loop's roles to write, run and hand them over (#1156)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GATEKEEPER = Path(__file__).resolve().parents[1] / "skills" / "gatekeeper"
LOOP = Path(__file__).resolve().parents[2] / "loop" / "skills" / "engineering-loop"
ACCEPTANCE = GATEKEEPER / "scripts" / "acceptance.py"
PASSING = "#!/bin/sh\necho checked\nexit 0\n"
FAILING = "#!/bin/sh\necho broken >&2\nexit 3\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def check(repo: Path, relative: str, body: str, executable: bool = True) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o755 if executable else 0o644)
    return path


def acceptance(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ACCEPTANCE), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def verdicts(out: str) -> list[str]:
    """Each PASS/FAIL line as `<word> <file>`, without its time."""
    return [
        " ".join(line.split()[:2])
        for line in out.splitlines()
        if line.startswith(("PASS ", "FAIL "))
    ]


def test_a_passing_and_a_failing_check_print_one_line_each_and_exit_1(repo: Path) -> None:
    check(repo, "acceptance/7/01-ok.sh", PASSING)
    check(repo, "acceptance/7/02-broken.sh", FAILING)

    result = acceptance(repo, "7")

    assert result.returncode == 1, result
    assert verdicts(result.stdout) == [
        "PASS acceptance/7/01-ok.sh",
        "FAIL acceptance/7/02-broken.sh",
    ]
    assert "TOTAL 2 checks, 1 passed, 0 skipped, 1 failed" in result.stdout
    assert "OVER BUDGET" not in result.stdout


def test_only_passing_checks_exit_0_in_name_order(repo: Path) -> None:
    check(repo, "acceptance/7/b.sh", PASSING)
    check(repo, "acceptance/7/a.sh", PASSING)
    check(repo, "acceptance/8/broken.sh", FAILING)

    result = acceptance(repo, "7")

    assert result.returncode == 0, result
    assert verdicts(result.stdout) == ["PASS acceptance/7/a.sh", "PASS acceptance/7/b.sh"]


def test_a_check_runs_from_the_repo_root_even_from_a_subfolder(repo: Path) -> None:
    (repo / "marker").write_text("here\n")
    check(repo, "acceptance/7/root.sh", "#!/bin/sh\ntest -f marker\n")
    (repo / "sub").mkdir()

    result = acceptance(repo / "sub", "#7")

    assert result.returncode == 0, result
    assert verdicts(result.stdout) == ["PASS acceptance/7/root.sh"]


def test_a_missing_folder_exits_2(repo: Path) -> None:
    check(repo, "acceptance/8/ok.sh", PASSING)

    result = acceptance(repo, "7")

    assert result.returncode == 2, result
    assert "acceptance/7/ does not exist" in result.stderr
    assert verdicts(result.stdout) == []


def test_a_folder_of_only_non_executable_files_exits_2(repo: Path) -> None:
    check(repo, "acceptance/7/README.md", "fixtures\n", executable=False)
    check(repo, "acceptance/7/ok.sh", PASSING, executable=False)
    check(repo, "acceptance/7/fixtures/data.sh", PASSING)

    result = acceptance(repo, "7")

    assert result.returncode == 2, result
    assert "NONE acceptance/7/ (no executable file)" in result.stdout
    assert verdicts(result.stdout) == []


def test_a_check_that_cannot_start_fails(repo: Path) -> None:
    check(repo, "acceptance/7/noshebang", "echo no interpreter line\n\0")

    result = acceptance(repo, "7")

    assert result.returncode == 1, result
    assert verdicts(result.stdout) == ["FAIL acceptance/7/noshebang"]


def test_all_runs_every_folder_in_issue_order_and_exits_1_when_one_fails(repo: Path) -> None:
    check(repo, "acceptance/10/ok.sh", PASSING)
    check(repo, "acceptance/9/broken.sh", FAILING)
    check(repo, "acceptance/9/ok.sh", PASSING)

    result = acceptance(repo, "--all")

    assert result.returncode == 1, result
    assert verdicts(result.stdout) == [
        "FAIL acceptance/9/broken.sh",
        "PASS acceptance/9/ok.sh",
        "PASS acceptance/10/ok.sh",
    ]


def test_all_skips_a_live_check_and_a_named_issue_runs_it(repo: Path) -> None:
    """#1386: the nightly has no live environment, so `--all` skips a `# acceptance: live` check, and a folder holding
    only such checks is not an empty one; run by its number the check runs."""
    check(repo, "acceptance/5/01-ok.sh", PASSING)
    check(repo, "acceptance/6/live.sh", "#!/bin/sh\n# acceptance: live\nexit 3\n")
    everything = acceptance(repo, "--all")
    assert everything.returncode == 0, everything.stdout + everything.stderr
    assert "SKIP acceptance/6/live.sh" in everything.stdout
    assert verdicts(everything.stdout) == ["PASS acceptance/5/01-ok.sh"]
    assert acceptance(repo, "6").returncode == 1


def test_all_skips_a_known_red_check_naming_its_issue_and_a_named_issue_runs_it(repo: Path) -> None:
    """A known-red check is skipped with its issue linked, never removed: one marker, `# acceptance: skip <link>`."""
    link = "https://github.com/o/r/issues/9"
    check(repo, "acceptance/5/01-ok.sh", PASSING)
    check(repo, "acceptance/6/red.sh", f"#!/bin/sh\n# acceptance: skip {link}\nexit 3\n")
    everything = acceptance(repo, "--all")
    assert everything.returncode == 0, everything.stdout + everything.stderr
    assert f"SKIP acceptance/6/red.sh (known red, tracked in {link})" in everything.stdout
    assert acceptance(repo, "6").returncode == 1


def test_a_skip_marker_without_an_issue_link_is_not_honoured_and_skips_are_counted(
    repo: Path,
) -> None:
    """The verifier's F1 and F2 (#2811): a known-red check hides only behind its linked issue, and `TOTAL` counts
    what was skipped, so passed + failed + skipped is every script found."""
    check(repo, "acceptance/5/01-ok.sh", PASSING)
    check(repo, "acceptance/6/nolink.sh", "#!/bin/sh\n# acceptance: skip\nexit 3\n")
    check(
        repo,
        "acceptance/7/linked.sh",
        "#!/bin/sh\n# acceptance: skip https://example.test/i/1\nexit 3\n",
    )
    check(repo, "acceptance/8/live.sh", "#!/bin/sh\n# acceptance: live\nexit 3\n")
    result = acceptance(repo, "--all")
    assert result.returncode == 1  # the unlinked skip ran, and failed
    assert verdicts(result.stdout) == ["PASS acceptance/5/01-ok.sh", "FAIL acceptance/6/nolink.sh"]
    assert "NOTE acceptance/6/nolink.sh: `# acceptance: skip` names no issue link" in result.stdout
    assert "TOTAL 4 checks, 1 passed, 2 skipped, 1 failed" in result.stdout


def test_all_exits_0_when_every_folder_passes(repo: Path) -> None:
    check(repo, "acceptance/9/ok.sh", PASSING)
    check(repo, "acceptance/10/ok.sh", PASSING)

    result = acceptance(repo, "--all")

    assert result.returncode == 0, result
    assert len(verdicts(result.stdout)) == 2


@pytest.mark.parametrize("layout", ["no folder", "empty folder"])
def test_all_with_nothing_to_run_exits_2(repo: Path, layout: str) -> None:
    if layout == "empty folder":
        check(repo, "acceptance/9/notes.md", "x\n", executable=False)

    assert acceptance(repo, "--all").returncode == 2


def test_all_with_one_folder_of_no_checks_exits_2_when_the_rest_pass(repo: Path) -> None:
    check(repo, "acceptance/9/ok.sh", PASSING)
    check(repo, "acceptance/10/notes.md", "x\n", executable=False)

    result = acceptance(repo, "--all")

    assert result.returncode == 2, result
    assert verdicts(result.stdout) == ["PASS acceptance/9/ok.sh"]


def budget(repo: Path, line: str) -> None:
    path = repo / "docs" / "agents" / "loop.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# Loop\n\n{line}\n")


@pytest.mark.parametrize(("body", "code"), [(PASSING, 0), (FAILING, 1)])
def test_over_the_spec_budget_prints_a_line_and_exits_on_the_checks(
    repo: Path, body: str, code: int
) -> None:
    budget(repo, "- `Acceptance budget: 0, 90`")
    check(repo, "acceptance/7/check.sh", body)

    result = acceptance(repo, "7")

    assert result.returncode == code, result
    assert sum(line.startswith("OVER BUDGET") for line in result.stdout.splitlines()) == 1
    assert "> 0 min, the spec budget" in result.stdout


def test_all_reads_the_nightly_budget(repo: Path) -> None:
    check(repo, "acceptance/7/ok.sh", PASSING)

    budget(repo, "Acceptance budget: 0, 90")
    assert "OVER BUDGET" not in acceptance(repo, "--all").stdout
    assert "OVER BUDGET" in acceptance(repo, "7").stdout

    (repo / "docs" / "agents" / "loop.md").write_text("Acceptance budget: 90, 0\n")
    over = acceptance(repo, "--all")
    assert over.returncode == 0, over
    assert "> 0 min, the nightly budget" in over.stdout


def test_a_malformed_budget_line_is_reported_and_the_defaults_apply(repo: Path) -> None:
    budget(repo, "Acceptance budget: soon")
    check(repo, "acceptance/7/ok.sh", PASSING)

    result = acceptance(repo, "7")

    assert result.returncode == 0, result
    assert "is not `<spec minutes>, <nightly minutes>`" in result.stderr
    assert "OVER BUDGET" not in result.stdout


def test_an_issue_that_is_not_a_number_is_a_usage_error(repo: Path) -> None:
    check(repo, "acceptance/7/ok.sh", PASSING)

    result = acceptance(repo, "../acceptance/7")

    assert result.returncode == 2, result
    assert "the issue is a number" in result.stderr
    assert verdicts(result.stdout) == []


def flat(name: str) -> str:
    return " ".join((LOOP / name).read_text().split())


def test_skill_states_the_acceptance_lines_and_names_the_runner() -> None:
    skill = flat("SKILL.md")
    assert "`Acceptance tests: <command>`" in skill
    assert "`Acceptance budget: <spec minutes>, <nightly minutes>`" in skill
    assert "`uv run <gatekeeper>/scripts/acceptance.py <issue>`" in skill
    assert "`acceptance/<issue>/`" in skill


def test_lead_spec_lines_name_their_check_and_the_proof_is_the_commands_log() -> None:
    lead = flat("lead.md")
    spec = lead[lead.index("2. **Spec.**") : lead.index("3. **Branch and notes.**")]
    prove = lead[lead.index("6. **Prove**") : lead.index("7. **Verify**")]
    assert "Before merge line ends with the check that runs it" in spec
    assert "`Manual:`" in spec
    assert "acceptance command's log" in prove
    assert "`Manual:` line" in prove


def test_worker_writes_the_checks_runs_the_command_and_reports_a_clean_tree() -> None:
    worker = flat("worker.md")
    build = worker[worker.index("1. **Build**") : worker.index("2. **Gates and push.**")]
    report = worker[worker.index("4. **Report.**") :]
    assert "scriptable Before merge line" in build
    assert "`acceptance/<issue>/`" in build
    assert "acceptance command" in report
    assert "the line `git status --porcelain: empty`" in report
