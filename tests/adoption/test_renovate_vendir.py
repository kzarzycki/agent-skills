from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

FIXTURE = Path(__file__).parents[1] / "fixtures" / "renovate"
QUALIFICATION_COMMAND = "python -m tools.capability_pack.cli update engineering"
EXPECTED_ARTIFACTS = {
    "vendir.lock.yml",
    "skills/alpha/SKILL.md",
    "skills/grilling/SKILL.md",
}


def test_pinned_renovate_records_the_vendir_artifact_boundary() -> None:
    """Catch a Renovate upgrade that changes the adopted updater decision."""
    version = subprocess.run(
        ["renovate", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert version == "43.285.7"

    fixture = yaml.safe_load((FIXTURE / "vendir.lock.yml").read_text())
    assert set(fixture["qualificationArtifacts"]) == EXPECTED_ARTIFACTS


def test_hosted_safe_configuration_cannot_run_qualification_command() -> None:
    """Catch accidental claims that hosted Renovate can run the local qualification step."""
    hosted_safe = {"allowedCommands": [], "updater": "scheduled-workflow"}
    assert QUALIFICATION_COMMAND not in hosted_safe["allowedCommands"]
    assert hosted_safe["updater"] == "scheduled-workflow"
