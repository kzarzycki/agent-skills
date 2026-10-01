from __future__ import annotations

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
from engineering.tests.e2e.live_contract import run_agent

WAYFINDER_SUPPORT = {
    "domain-modeling",
    "grilling",
    "prototype",
    "research",
}


def test_apm_targets_receive_complete_canonical_inventory(tmp_path: Path) -> None:
    fixture = install_fixture(tmp_path)
    source = file_manifest(PACKAGE / "skills")

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
