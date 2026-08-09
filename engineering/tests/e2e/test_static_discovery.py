from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from engineering.tests.e2e.conformance import (
    CLAUDE,
    CODEX,
    PACKAGE,
    TargetAdapter,
    assert_catalog_matches,
    file_manifest,
    install_fixture,
    local_reference_failures,
    pack_catalog,
)
from engineering.tests.e2e.live_contract import AgentHarness, run_agent
from engineering.tests.test_setup_skill import _fixture_project, _run_fixture_protocol

WAYFINDER_SUPPORT = {
    "domain-modeling",
    "grilling",
    "prototype",
    "research",
    "setup-engineering-workflow-for-apm",
}


def test_apm_targets_receive_complete_canonical_inventory(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)
    source = file_manifest(PACKAGE / "skills")

    assert len(source) == 63
    assert_catalog_matches(source, fixture.catalog(CLAUDE))
    assert_catalog_matches(source, fixture.catalog(CODEX))
    assert fixture.catalog(CLAUDE).skill_names == fixture.expected_skills
    assert fixture.catalog(CODEX).skill_names == fixture.expected_skills
    assert WAYFINDER_SUPPORT <= fixture.catalog(CLAUDE).skill_names
    assert WAYFINDER_SUPPORT <= fixture.catalog(CODEX).skill_names


@pytest.mark.parametrize("mutation", ["omit", "corrupt"])
def test_complete_inventory_rejects_symmetric_target_mutation(
    mutation: str,
    tmp_path: Path,
) -> None:
    fixture = install_fixture(tmp_path)
    source = file_manifest(PACKAGE / "skills")
    relative = Path("prototype/agents/openai.yaml")
    for adapter in (CLAUDE, CODEX):
        target = fixture.catalog(adapter).root / relative
        if mutation == "omit":
            target.unlink()
        else:
            target.write_bytes(b"corrupt")

    for adapter in (CLAUDE, CODEX):
        with pytest.raises(AssertionError, match=str(relative)):
            assert_catalog_matches(source, fixture.catalog(adapter))


def test_wayfinder_is_byte_identical_across_canonical_and_targets(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)
    source = (PACKAGE / "skills" / "wayfinder" / "SKILL.md").read_bytes()

    assert fixture.catalog(CLAUDE).file_bytes("wayfinder") == source
    assert fixture.catalog(CODEX).file_bytes("wayfinder") == source


def test_deployed_relative_references_and_packaged_scripts_resolve(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)
    source = file_manifest(PACKAGE / "skills")

    assert local_reference_failures(fixture.catalog(CLAUDE).root) == []
    assert local_reference_failures(fixture.catalog(CODEX).root) == []
    assert fixture.catalog(CLAUDE).script_manifest
    assert_catalog_matches(source, fixture.catalog(CLAUDE))
    assert_catalog_matches(source, fixture.catalog(CODEX))


def test_setup_protocol_is_discoverable_in_both_catalogs(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)

    for adapter in (CLAUDE, CODEX):
        setup = fixture.catalog(adapter).skill_root("setup-engineering-workflow-for-apm")
        skill = (setup / "SKILL.md").read_text()
        assert "<!-- setup-fixture-protocol" in skill
        assert (setup / "templates" / "project-guidance.md").is_file()
        assert (setup / "templates" / "issue-tracker-github.md").is_file()


@pytest.mark.parametrize("mutation", ["omit", "corrupt"])
def test_neutral_catalog_adapter_detects_artifact_mutation(
    mutation: str,
    tmp_path: Path,
) -> None:
    package_before = file_manifest(PACKAGE / "skills")
    dependency = PACKAGE / "tests" / "consumer" / "apm.yml"
    dependency_before = dependency.read_bytes()
    artifact = pack_catalog(tmp_path)
    adapter = TargetAdapter("catalog-reader-fixture", Path("skills"))
    catalog = adapter.catalog(artifact)
    assert_catalog_matches(package_before, catalog)

    target = catalog.root / "prototype" / "agents" / "openai.yaml"
    if mutation == "omit":
        target.unlink()
    else:
        target.write_bytes(b"corrupt")

    with pytest.raises(AssertionError, match="prototype/agents/openai.yaml"):
        assert_catalog_matches(package_before, catalog)
    assert file_manifest(PACKAGE / "skills") == package_before
    assert dependency.read_bytes() == dependency_before
    assert "catalog-reader-fixture" not in (PACKAGE / "apm.yml").read_text()


def test_installation_does_not_leak_global_catalog_content(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)

    assert fixture.global_catalogs_before == fixture.global_catalogs_after


@pytest.mark.parametrize("approved", [False, True])
def test_setup_confirmation_controls_exact_sync_without_github_mutation(
    approved: bool,
    tmp_path: Path,
) -> None:
    project = _fixture_project(tmp_path)
    harness = AgentHarness.create("claude", tmp_path / "harness")

    result = _run_fixture_protocol(project, source_changes_approved=approved)
    for command in result["sync_commands"]:
        completed = subprocess.run(
            command,
            cwd=project,
            env=harness.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    if approved:
        assert harness.mise_calls == (("run", "agent-sync"),)
        assert set(result["directly_written_files"]) == {
            ".apm/instructions/engineering-workflow.md",
            "docs/agents/issue-tracker.md",
        }
    else:
        assert harness.mise_calls == ()
        assert result["directly_written_files"] == []
    assert harness.github_mutations == ()


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_run_agent_uses_isolated_config_without_stderr_assumptions(
    agent: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = tmp_path / "agent-bin"
    bin_dir.mkdir()
    executable = bin_dir / agent
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os\n"
        "from pathlib import Path\n"
        "print(f\"HOME={os.environ['HOME']}\")\n"
        "print(f\"CLAUDE_CONFIG_DIR={os.environ['CLAUDE_CONFIG_DIR']}\")\n"
        "print(f\"CODEX_HOME={os.environ['CODEX_HOME']}\")\n"
        'print(f"CWD={Path.cwd()}")\n'
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{Path('/usr/bin')}:{Path('/bin')}")
    repo = tmp_path / "repository"
    repo.mkdir()

    result = run_agent(agent, "fixture prompt", repo)

    assert result.exit_code == 0
    assert result.activation_skills == ()
    assert result.evidence_paths == ()
    assert f"CWD={repo}" in result.stdout
    assert f"HOME={Path.home()}" not in result.stdout
