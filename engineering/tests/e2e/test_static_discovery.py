from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engineering.tests.e2e.conformance import (
    CLAUDE,
    CODEX,
    PACKAGE,
    SkillCatalog,
    TargetAdapter,
    file_manifest,
    install_fixture,
    local_reference_failures,
)
from engineering.tests.e2e.live_contract import EVIDENCE_PATHS, run_agent

WAYFINDER_SUPPORT = {
    "domain-modeling",
    "grilling",
    "prototype",
    "research",
    "setup-engineering-workflow-for-apm",
}


def test_apm_targets_receive_identical_provenance_inventory_and_wayfinder(
    tmp_path: Path,
) -> None:
    fixture = install_fixture(tmp_path)

    assert fixture.catalog(CLAUDE).skill_names == fixture.expected_skills
    assert fixture.catalog(CODEX).skill_names == fixture.expected_skills
    assert fixture.catalog(CLAUDE).file_bytes("wayfinder") == fixture.catalog(CODEX).file_bytes(
        "wayfinder"
    )
    assert (
        fixture.catalog(CLAUDE).file_bytes("wayfinder")
        == (PACKAGE / "skills" / "wayfinder" / "SKILL.md").read_bytes()
    )
    assert WAYFINDER_SUPPORT <= fixture.catalog(CLAUDE).skill_names
    assert WAYFINDER_SUPPORT <= fixture.catalog(CODEX).skill_names


def test_deployed_relative_references_and_packaged_scripts_resolve(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)
    source_scripts = SkillCatalog(PACKAGE / "skills").script_manifest

    assert local_reference_failures(fixture.catalog(CLAUDE).root) == []
    assert local_reference_failures(fixture.catalog(CODEX).root) == []
    assert fixture.catalog(CLAUDE).script_manifest == source_scripts
    assert fixture.catalog(CODEX).script_manifest == source_scripts
    assert source_scripts


def test_setup_protocol_is_discoverable_in_both_catalogs(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)

    for adapter in (CLAUDE, CODEX):
        setup = fixture.catalog(adapter).skill_root("setup-engineering-workflow-for-apm")
        skill = (setup / "SKILL.md").read_text()
        assert "<!-- setup-fixture-protocol" in skill
        assert (setup / "templates" / "project-guidance.md").is_file()
        assert (setup / "templates" / "issue-tracker-github.md").is_file()


def test_synthetic_adapter_extends_catalog_without_changing_package_or_dependency(
    tmp_path: Path,
) -> None:
    fixture = install_fixture(tmp_path)
    package_before = file_manifest(PACKAGE / "skills")
    dependency_before = (fixture.consumer / "apm.yml").read_bytes()
    synthetic = TargetAdapter("synthetic-coding-agent", Path(".synthetic/skills"))
    shutil.copytree(fixture.catalog(CLAUDE).root, fixture.consumer / synthetic.catalog_path)

    assert fixture.catalog(synthetic).skill_names == fixture.expected_skills
    assert file_manifest(PACKAGE / "skills") == package_before
    assert (fixture.consumer / "apm.yml").read_bytes() == dependency_before
    assert "synthetic-coding-agent" not in (PACKAGE / "apm.yml").read_text()


def test_installation_does_not_leak_into_real_user_catalogs(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)

    assert fixture.global_catalogs_before == fixture.global_catalogs_after


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_run_agent_uses_isolated_config_and_reports_evidence(
    agent: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bin_dir = tmp_path / "agent-bin"
    bin_dir.mkdir()
    executable = bin_dir / agent
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "from pathlib import Path\n"
        "print(f\"HOME={os.environ['HOME']}\")\n"
        "print(f\"CLAUDE_CONFIG_DIR={os.environ['CLAUDE_CONFIG_DIR']}\")\n"
        "print(f\"CODEX_HOME={os.environ['CODEX_HOME']}\")\n"
        'print(f"CWD={Path.cwd()}")\n'
        'print("EVIDENCE: README.md")\n'
        'print("EVIDENCE: src/domain.py")\n'
        'print("EVIDENCE: tests/test_domain.py")\n'
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{Path('/usr/bin')}:{Path('/bin')}")
    repo = tmp_path / "repository"
    repo.mkdir()

    result = run_agent(agent, "fixture prompt", repo)

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.evidence_paths == EVIDENCE_PATHS
    assert f"CWD={repo}" in result.stdout
    assert f"HOME={Path.home()}" not in result.stdout
