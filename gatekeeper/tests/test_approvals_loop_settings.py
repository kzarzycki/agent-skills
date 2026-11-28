"""loop.md's `## Loop settings` block (#2830): every value a script reads sits in one fenced yaml block that one loader reads
(gatekeeper.py's loop_setting), as gatekeeper.md's policy does. A key set in the block reaches each reader, an unknown key
or a wrong type is refused naming the key, a key set in the block and as its old line is refused, and loop-migrate writes
the block from the old lines so that every value reads back the same."""

from __future__ import annotations

import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest
from approvals_harness import approvals
from test_acceptance import ACCEPTANCE, check, repo  # noqa: F401
from test_approvals_acceptance_evidence import LOOP as POLICY_LOOP
from test_approvals_acceptance_evidence import acceptance_lines, briefing  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "loop-project" / "docs" / "agents" / "loop.md"


def loop(body: str) -> str:
    """A loop.md whose `## Loop settings` block holds `body`, with prose around it."""
    return f"# Loop facts\n\nProse an agent reads.\n\n## Loop settings\n\n```yaml\n{body}```\n\n## Approvals\n\nMore prose.\n"


def refused(text: str, key: str) -> str:
    """The refusal reading `key` of `text` gives; it names the key."""
    with pytest.raises(approvals.Refused) as caught:
        approvals.loop_setting(text, key)
    return str(caught.value)


def test_affected_tests_in_the_block_is_the_command_narrowing_reads() -> None:
    text = loop("affected_tests: mise run check-affected\n")
    assert approvals.loop_setting(text, "affected_tests") == "mise run check-affected"
    assert approvals.narrowing(text) == "mise run check-affected"


def test_test_report_in_the_block_is_the_path_the_rerun_counts_tests_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = loop("test_report: .qualify/junit.xml\n")
    assert approvals.loop_setting(text, "test_report") == ".qualify/junit.xml"
    seen: list[str] = []
    monkeypatch.setattr(approvals, "toplevel", lambda: tmp_path)
    monkeypatch.setattr(approvals, "affected_tests", lambda base, text=None: seen.append(text) or 0)
    report = tmp_path / ".qualify" / "junit.xml"
    report.parent.mkdir()
    report.write_text("<testsuite/>")
    approvals.rerun("abc", "base", text, False)
    assert seen == [text] and not report.exists()  # the rerun removed the report the block names


def test_gate_full_in_the_block_opts_out_of_narrowing() -> None:
    text = loop("affected_tests: mise run check-affected\ngate: full\n")
    assert approvals.loop_setting(text, "gate") == "full"
    assert approvals.narrowing(text) is None
    assert "gate" in refused(loop("gate: nightly\n"), "gate")


def test_gate_base_in_the_block_names_the_variable_the_selection_reads() -> None:
    text = loop("gate_base: LOOP_BASE\n")
    assert approvals.gate_base_variable(text) == "LOOP_BASE"
    assert approvals.gate_base_variable(loop("gate: full\n")) == "GATE_BASE"
    assert "gate_base" in refused(loop("gate_base: not-a-name\n"), "gate_base")


def test_gate_base_in_the_block_is_the_variable_a_plain_gate_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(loop("gate_base: LOOP_BASE\n"))
    monkeypatch.setattr(approvals, "toplevel", lambda: tmp_path)
    monkeypatch.setattr(approvals, "local_ci_env", list)
    monkeypatch.setenv("LOOP_BASE", "abc")
    assert "LOOP_BASE" not in approvals.gate_env({"sets": {}})


def checkout_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "docs" / "agents").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(text)
    monkeypatch.chdir(tmp_path)


def test_gate_cost_in_the_block_sets_what_the_host_slot_count_follows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout_with(tmp_path, monkeypatch, loop("gate_cost:\n  cores: 4\n  gb: 8\n  reserve_gb: 2\n"))
    assert approvals.gate_cost() == ((Fraction(4), Fraction(8)), Fraction(2))
    checkout_with(tmp_path, monkeypatch, loop("gate_cost:\n  cores: 2.5\n  gb: 6\n"))
    assert approvals.gate_cost() == ((Fraction(5, 2), Fraction(6)), None)
    checkout_with(tmp_path, monkeypatch, loop("gate_cost:\n  cores: 0\n  gb: 6\n"))
    with pytest.raises(approvals.Refused, match="gate_cost"):
        approvals.gate_cost()


def test_wall_clock_variable_in_the_block_names_the_variable_drift_is_checked_in(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(
        loop("wall_clock_variable: SELECT_SECONDS\n")
    )
    (tmp_path / "mise.toml").write_text('[env]\nSELECT_SECONDS = "1800"\n')
    drift = approvals.limit_drift(tmp_path, None)
    assert any("mise.toml: `SELECT_SECONDS` is 1800 seconds" in line for line in drift)


def test_acceptance_tests_in_the_block_is_the_command_the_brief_names() -> None:
    text = loop("acceptance:\n  tests: mise run acceptance --\n")
    assert approvals.loop_setting(text, "acceptance.tests") == "mise run acceptance --"
    assert approvals.loop_setting(loop("gate: full\n"), "acceptance.tests") is None


def test_acceptance_tests_in_the_block_is_the_command_brief_prints_for_each_spec(
    briefing: dict[str, object],
    capsys: pytest.CaptureFixture[str],
) -> None:
    briefing["loop"] = POLICY_LOOP + "\n" + loop("acceptance:\n  tests: mise run acceptance\n")
    briefing["body"] = "Closes #12.\n"
    assert approvals.main(["brief", "7"]) == 0
    assert acceptance_lines(capsys) == ["- Acceptance tests: mise run acceptance 12"]


def test_acceptance_budget_in_the_block_is_the_runners_budget(repo: Path) -> None:
    path = repo / "docs" / "agents" / "loop.md"
    path.parent.mkdir(parents=True)
    path.write_text(loop("acceptance:\n  budget:\n    spec: 0\n    nightly: 90\n"))
    check(repo, "acceptance/7/check.sh", "#!/bin/sh\nexit 0\n")
    result = subprocess.run(
        [sys.executable, str(ACCEPTANCE), "7"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result
    assert "> 0 min, the spec budget" in result.stdout


def test_a_budget_off_its_schema_stops_the_acceptance_runner_naming_the_key(repo: Path) -> None:
    path = repo / "docs" / "agents" / "loop.md"
    path.parent.mkdir(parents=True)
    path.write_text(loop("acceptance:\n  budget:\n    spec: soon\n    nightly: 90\n"))
    check(repo, "acceptance/7/check.sh", "#!/bin/sh\nexit 0\n")
    result = subprocess.run(
        [sys.executable, str(ACCEPTANCE), "7"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "acceptance.budget.spec" in result.stderr


def test_a_budget_off_its_schema_runs_no_check_at_all(repo: Path) -> None:
    path = repo / "docs" / "agents" / "loop.md"
    path.parent.mkdir(parents=True)
    path.write_text(loop("acceptance:\n  budget:\n    spec: soon\n    nightly: 90\n"))
    marker = repo / "ran"
    check(repo, "acceptance/7/check.sh", f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    result = subprocess.run(
        [sys.executable, str(ACCEPTANCE), "7"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0 and "PASS" not in result.stdout
    assert not marker.exists()


def test_cloud_worker_in_the_block_is_none_or_an_agent_with_its_gate_and_env() -> None:
    assert approvals.loop_setting(loop("cloud_worker: none\n"), "cloud_worker") == "none"
    held = approvals.loop_setting(
        loop("cloud_worker:\n  agent: claude-cloud\n  gate: test\n  env: dev\n"), "cloud_worker"
    )
    assert held == {"agent": "claude-cloud", "gate": "test", "env": "dev"}
    assert approvals.loop_setting(loop("cloud_worker:\n  gate: test\n"), "cloud_worker") == {
        "agent": "claude-cloud",
        "gate": "test",
        "env": "",
    }
    assert "cloud_worker" in refused(loop("cloud_worker: maybe\n"), "cloud_worker")


def test_placement_in_the_block_is_one_value_hosts_or_a_place() -> None:
    hosts = approvals.loop_setting(loop("placement:\n  hosts: [box, mac]\n"), "placement")
    assert hosts == {"hosts": ["box", "mac"]}
    assert approvals.loop_setting(loop("placement: CI\n"), "placement") == "CI"
    assert approvals.loop_setting(loop("placement: same machine\n"), "placement") == "same machine"
    assert "placement" in refused(loop("placement: elsewhere\n"), "placement")


def test_models_in_the_block_hold_a_tier_and_condition_for_each_role() -> None:
    text = loop(
        "models:\n  lead: mid for size:S or smaller\n  worker: mid for size:S or smaller\n"
        "  verifier: mid for not risk:high\n"
    )
    assert approvals.loop_setting(text, "models.lead") == "mid for size:S or smaller"
    assert approvals.loop_setting(text, "models.worker") == "mid for size:S or smaller"
    assert approvals.loop_setting(text, "models.verifier") == "mid for not risk:high"
    assert "models.lead" in refused(loop("models:\n  lead: 3\n"), "models.lead")


def test_lead_autocompact_in_the_block_is_a_size() -> None:
    assert approvals.loop_setting(loop("lead_autocompact: 200k\n"), "lead_autocompact") == "200k"
    assert (
        approvals.loop_setting(loop("lead_autocompact: 150000\n"), "lead_autocompact") == "150000"
    )
    assert "lead_autocompact" in refused(loop("lead_autocompact: [1]\n"), "lead_autocompact")


def test_tools_in_the_block_are_full_or_a_list_for_each_lean_role() -> None:
    text = loop("tools:\n  worker: [WebFetch, github]\n  verifier: full\n")
    assert approvals.loop_setting(text, "tools.worker") == ["WebFetch", "github"]
    assert approvals.loop_setting(text, "tools.verifier") == "full"
    assert "tools.worker" in refused(loop("tools:\n  worker: some\n"), "tools.worker")


def test_verifier_session_in_the_block_is_reuse_or_fresh() -> None:
    assert approvals.loop_setting(loop("verifier_session: reuse\n"), "verifier_session") == "reuse"
    assert "verifier_session" in refused(loop("verifier_session: always\n"), "verifier_session")


def test_orchestration_backend_in_the_block_is_a_backend_name() -> None:
    assert (
        approvals.loop_setting(loop("orchestration_backend: omnigent\n"), "orchestration_backend")
        == "omnigent"
    )
    assert "orchestration_backend" in refused(
        loop("orchestration_backend: carrier\n"), "orchestration_backend"
    )


@pytest.mark.parametrize(
    ("body", "named"),
    [
        ("afected_tests: mise run x\n", "afected_tests"),
        ("gate_cost:\n  cores: 4\n  gb: 8\n  cors: 2\n", "gate_cost.cors"),
        ("models:\n  leed: mid for x\n", "models.leed"),
        ("something_else: 1\n", "something_else"),
    ],
)
def test_a_misspelt_or_unknown_key_is_refused_naming_it(body: str, named: str) -> None:
    assert named in refused(loop(body), "gate")


def test_a_misspelt_key_is_refused_by_the_reader_too() -> None:
    with pytest.raises(approvals.Refused, match="afected_tests"):
        approvals.narrowing(loop("afected_tests: mise run x\n"))


@pytest.mark.parametrize(
    ("body", "named"),
    [
        ("affected_tests: 3\n", "affected_tests"),
        ("test_report: [a]\n", "test_report"),
        ("gate_cost:\n  cores: many\n  gb: 8\n", "gate_cost.cores"),
        ("gate_cost:\n  cores: 4\n", "gate_cost"),
        ("acceptance:\n  tests: true\n", "acceptance.tests"),
        ("wall_clock_variable: 1x\n", "wall_clock_variable"),
    ],
)
def test_a_wrong_type_is_refused_naming_the_key(body: str, named: str) -> None:
    assert named in refused(loop(body), "gate")


def test_a_key_set_twice_in_the_block_is_refused() -> None:
    assert "gate_base" in refused(loop("gate_base: A\ngate_base: B\n"), "gate_base")


def test_a_heading_with_no_block_is_refused() -> None:
    with pytest.raises(approvals.Refused, match="Loop settings"):
        approvals.loop_setting("# Loop\n\n## Loop settings\n\nno block\n", "gate")


@pytest.mark.parametrize(
    ("body", "line", "key"),
    [
        ("affected_tests: a\n", "Affected tests: b", "affected_tests"),
        ("test_report: a\n", "Test report: b", "test_report"),
        ("gate: full\n", "Gate: full", "gate"),
        ("gate_base: A\n", "Gate base: B", "gate_base"),
        ("gate_cost: {cores: 1, gb: 1}\n", "Gate cost: 1 cores, 1 GB", "gate_cost"),
        ("wall_clock_variable: A\n", "Wall-clock variable: B", "wall_clock_variable"),
        ("acceptance: {tests: a}\n", "Acceptance tests: b", "acceptance.tests"),
        (
            "acceptance: {budget: {spec: 1, nightly: 2}}\n",
            "Acceptance budget: 1, 2",
            "acceptance.budget",
        ),
        ("cloud_worker: none\n", "Cloud worker: none", "cloud_worker"),
        ("placement: CI\n", "Placement: CI", "placement"),
        ("placement: CI\n", "Verifier hosts: a", "placement"),
        ("models: {lead: mid for x}\n", "Lead model: mid for x", "models.lead"),
        ("models: {worker: mid for x}\n", "Worker model: mid for x", "models.worker"),
        ("models: {verifier: mid for x}\n", "Verifier model: mid for x", "models.verifier"),
        ("lead_autocompact: 200k\n", "Lead autocompact: 200k", "lead_autocompact"),
        ("tools: {worker: full}\n", "Worker tools: full", "tools.worker"),
        ("tools: {verifier: full}\n", "Verifier tools: full", "tools.verifier"),
        ("verifier_session: reuse\n", "Verifier session: reuse", "verifier_session"),
        (
            "orchestration_backend: native\n",
            "Orchestration backend: native",
            "orchestration_backend",
        ),
    ],
)
def test_a_key_in_the_block_and_as_its_old_line_is_refused_naming_the_key(
    body: str, line: str, key: str
) -> None:
    text = loop(body) + f"\n{line}\n"
    message = refused(text, "gate")
    assert f"`{key}`" in message and line.split(":")[0] in message


def test_a_key_the_block_leaves_out_still_reads_from_its_old_line() -> None:
    text = loop("gate_base: A\n") + "\nAffected tests: mise run x\n"
    assert approvals.loop_setting(text, "affected_tests") == "mise run x"
    assert approvals.loop_setting(text, "gate_base") == "A"


OLD_LINES = """# Loop

Orchestration backend: omnigent
Affected tests: mise run check-affected
Test report: .qualify/junit.xml
Gate: full
Gate base: LOOP_BASE
Gate cost: 4 cores, 8 GB, reserve 2 GB
Wall-clock variable: SELECT_SECONDS
Acceptance tests: mise run acceptance --
Acceptance budget: 10, 90
Cloud worker: claude-cloud, gate test, env dev
Placement: hosts: box, mac
Worker model: mid for size:S or smaller
Verifier model: mid for not risk:high
Lead model: mid for size:S or smaller
Lead autocompact: 200k
Worker tools: WebFetch, github
Verifier tools: full
Verifier session: reuse
Standing decisions: docs/decisions.md

## Approvals

Prose stays.
"""


def read_all(text: str) -> dict[str, object]:
    return {key: approvals.loop_setting(text, key) for key in approvals.LOOP_LABELS}


def test_a_loop_md_with_old_lines_only_reads_as_it_always_did() -> None:
    held = read_all(OLD_LINES)
    assert held["affected_tests"] == "mise run check-affected"
    assert held["gate"] == "full" and held["gate_base"] == "LOOP_BASE"
    assert held["gate_cost"] == {"cores": Fraction(4), "gb": Fraction(8), "reserve_gb": Fraction(2)}
    assert held["acceptance.budget"] == (10.0, 90.0)
    assert held["cloud_worker"] == {"agent": "claude-cloud", "gate": "test", "env": "dev"}
    assert held["placement"] == {"hosts": ["box", "mac"]}
    assert held["tools.worker"] == ["WebFetch", "github"] and held["tools.verifier"] == "full"
    assert held["orchestration_backend"] == "omnigent"


def test_migrate_turns_old_lines_into_a_block_that_reads_the_same() -> None:
    migrated = approvals.loop_migrate(OLD_LINES)
    assert "## Loop settings" in migrated and "\n## Settings" not in migrated
    assert read_all(migrated) == read_all(OLD_LINES)
    assert (
        "Affected tests:" not in migrated and "Placement:" not in migrated
    )  # the old lines are removed
    assert "Standing decisions: docs/decisions.md" in migrated and "Prose stays." in migrated
    assert approvals.loop_migrate.__doc__ and approvals.loop_block(migrated)
    with pytest.raises(approvals.Refused, match="already"):
        approvals.loop_migrate(migrated)


def test_migrate_keeps_a_cloud_worker_none_reason_as_a_comment() -> None:
    migrated = approvals.loop_migrate("# Loop\n\nCloud worker: none, heavy runs stay on hosts\n")
    assert "cloud_worker: none  # heavy runs stay on hosts" in migrated
    assert approvals.loop_setting(migrated, "cloud_worker") == "none"


def test_migrate_refuses_a_line_the_block_cannot_hold_naming_the_key() -> None:
    with pytest.raises(approvals.Refused, match="placement"):
        approvals.loop_migrate("# Loop\n\nPlacement: somewhere else\n")


@pytest.mark.parametrize(
    "path", [FIXTURE, ROOT / "docs" / "agents" / "loop.md"], ids=["fixture", "repo"]
)
def test_migrate_reads_back_the_files_it_is_run_on(path: Path) -> None:
    text = path.read_text()
    assert read_all(approvals.loop_migrate(text)) == read_all(text)


def test_loop_migrate_prints_the_file_and_write_replaces_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "loop.md"
    target.write_text(OLD_LINES)
    assert approvals.main(["loop-migrate", str(target)]) == 0
    printed = capsys.readouterr().out
    assert target.read_text() == OLD_LINES and read_all(printed) == read_all(OLD_LINES)
    assert approvals.main(["loop-migrate", str(target), "--write"]) == 0
    assert target.read_text() == printed


def test_the_block_is_not_the_deprecated_policy_location() -> None:
    """`## Loop settings` is no `## Settings`: a loop.md with the block and a gatekeeper.md policy is no two policies."""
    policy = "# Gatekeeper\n\n## Policy\n\n```yaml\nloop:\n  cap: 3\n```\n"
    text = loop("gate_base: A\n")
    chosen = approvals.chosen(text, policy)
    assert isinstance(chosen, approvals.Policy)
    assert approvals.settings(chosen)["cap"] == 3


def held_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, variable: str) -> None:
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(text)
    monkeypatch.setattr(approvals, "toplevel", lambda: tmp_path)
    monkeypatch.setattr(approvals, "local_ci_env", list)
    monkeypatch.setenv(variable, "foreign")
    approvals.loop_block.cache_clear()


def test_an_old_gate_base_line_with_trailing_punctuation_still_clears_its_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As on main, `Gate base: CUSTOM_BASE,` and a sentence after it names the variable a plain gate clears."""
    held_loop(
        tmp_path,
        monkeypatch,
        "# Loop\n\nGate base: CUSTOM_BASE, the selection's base.\n",
        "CUSTOM_BASE",
    )
    assert "CUSTOM_BASE" not in approvals.gate_env({"sets": {}})


def test_a_block_the_loader_refuses_never_leaves_the_gate_base_variable_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held_loop(
        tmp_path,
        monkeypatch,
        loop("gate_base: CUSTOM_BASE\nafected_tests: mise run x\n"),
        "CUSTOM_BASE",
    )
    with pytest.raises(approvals.Refused, match="afected_tests"):
        approvals.gate_env({"sets": {}})


def test_a_second_yaml_block_under_loop_settings_is_refused_naming_it() -> None:
    text = (
        "# Loop\n\n## Loop settings\n\n```yaml\ngate: full\n```\n\nMore.\n\n"
        "```yaml\nafected_tests: mise run x\n```\n"
    )
    approvals.loop_block.cache_clear()
    with pytest.raises(approvals.Refused, match="second.*afected_tests"):
        approvals.loop_setting(text, "gate")


def test_a_repeated_loop_settings_heading_is_refused_naming_it() -> None:
    text = (
        "# Loop\n\n## Loop settings\n\n```yaml\ngate: full\n```\n\n## Notes\n\nProse.\n\n"
        "## Loop settings\n\n```yaml\nafected_tests: mise run x\n```\n"
    )
    approvals.loop_block.cache_clear()
    with pytest.raises(approvals.Refused, match="## Loop settings heading more than once"):
        approvals.loop_setting(text, "gate")
    with pytest.raises(approvals.Refused, match="## Loop settings"):
        approvals.loop_migrate(text)  # the migration reads no block it would leave behind


@pytest.mark.parametrize(
    ("body", "named"),
    [
        ("gate_cost: {cores: .inf, gb: 8}\n", "gate_cost.cores"),
        ("gate_cost: {cores: 4, gb: .nan}\n", "gate_cost.gb"),
        ("acceptance: {budget: {spec: .nan, nightly: 90}}\n", "acceptance.budget.spec"),
        ("acceptance: {budget: {spec: 10, nightly: -.inf}}\n", "acceptance.budget.nightly"),
    ],
)
def test_a_non_finite_number_is_refused_naming_the_key(body: str, named: str) -> None:
    approvals.loop_block.cache_clear()
    assert named in refused(loop(body), named.split(".")[0])
