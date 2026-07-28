from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).parents[1] / "fixtures" / "renovate"
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
