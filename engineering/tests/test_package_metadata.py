from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

REPOSITORY = Path(__file__).resolve().parents[2]
PACKAGE = REPOSITORY / "engineering"
EXPECTED_VERSION = "0.2.0"
QUALIFICATION_STAGE_ROOT = "CAPABILITY_PACK_QUALIFICATION_STAGE_ROOT"


def test_apm_and_claude_metadata_publish_the_same_independent_package() -> None:
    apm_manifest = yaml.safe_load((PACKAGE / "apm.yml").read_text())
    plugin_manifest = json.loads((PACKAGE / ".claude-plugin" / "plugin.json").read_text())

    assert apm_manifest["name"] == "engineering"
    assert apm_manifest["version"] == EXPECTED_VERSION
    assert apm_manifest["targets"] == ["claude", "codex"]
    assert apm_manifest["dependencies"] == {"apm": [], "mcp": []}
    assert plugin_manifest["name"] == "engineering"
    assert plugin_manifest["version"] == EXPECTED_VERSION


def test_claude_marketplace_exposes_only_the_owned_engineering_package() -> None:
    marketplace_path = REPOSITORY / ".claude-plugin" / "marketplace.json"
    stage_root = os.environ.get(QUALIFICATION_STAGE_ROOT)
    if stage_root is not None:
        assert Path(stage_root).resolve() == PACKAGE.resolve()
        pytest.skip("repository marketplace is outside the explicit package stage")
    marketplace = json.loads(marketplace_path.read_text())
    engineering_entries = [
        plugin for plugin in marketplace["plugins"] if plugin["name"] == "engineering"
    ]

    assert len(engineering_entries) == 1
    assert engineering_entries[0]["source"] == "./engineering"
    assert not any(plugin["name"] == "mattpocock-skills" for plugin in marketplace["plugins"])


def test_consumer_contract_uses_one_versioned_virtual_subdirectory_dependency() -> None:
    consumer = yaml.safe_load((PACKAGE / "tests" / "consumer" / "apm.yml").read_text())

    assert consumer["targets"] == ["claude", "codex"]
    assert consumer["dependencies"] == {
        "apm": [
            {
                "git": "kzarzycki/agent-skills/engineering",
                "ref": "^0.2.0",
            }
        ],
        "mcp": [],
    }
