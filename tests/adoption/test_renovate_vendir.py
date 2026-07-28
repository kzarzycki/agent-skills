from __future__ import annotations

import json
import tomllib
from pathlib import Path

FIXTURE = Path(__file__).parents[1] / "fixtures" / "renovate"
ROOT = Path(__file__).parents[2]
QUALIFICATION_COMMAND = "python -m tools.capability_pack.cli update engineering"


def test_real_renovate_probe_records_why_scheduled_workflow_is_required() -> None:
    """Keep the one-time Renovate 43.285.7 dry-run result reviewable."""
    records = [
        json.loads(line) for line in (FIXTURE / "renovate-dry-run.jsonl").read_text().splitlines()
    ]

    assert records[0]["renovateVersion"] == "43.285.7"
    extracted = next(record for record in records if record["msg"] == "packageFiles with updates")
    dependencies = extracted["config"]["vendir"][0]["deps"]
    assert len(dependencies) == 2
    assert {dependency["skipReason"] for dependency in dependencies} == {"invalid-value"}
    assert records[-1]["msg"] == "Repository finished"


def test_hosted_configuration_cannot_run_qualification_command() -> None:
    """Hosted Renovate has no command boundary for the qualification step."""
    boundary = json.loads((FIXTURE / "hosted-boundary.json").read_text())

    assert QUALIFICATION_COMMAND not in boundary["allowedCommands"]
    assert QUALIFICATION_COMMAND not in boundary["postUpgradeTasks"]["commands"]
    assert boundary["updater"] == "scheduled-workflow"


def test_probe_task_pins_runtime_and_explicit_renovate_download() -> None:
    config = tomllib.loads((ROOT / "mise.toml").read_text())

    assert config["tools"]["node"] == "24.18.0"
    assert all("renovate" not in tool for tool in config["tools"])
    task = config["tasks"]["probe-renovate-vendir"]
    assert task["dir"] == "tests/fixtures/renovate"
    assert "gtimeout 120" in task["run"]
    assert "npx --yes renovate@43.285.7" in task["run"]
    assert "--platform=local" in task["run"]
    assert "--dry-run=full" in task["run"]
    assert "--require-config=required" in task["run"]
    assert "--binary-source=global" in task["run"]
