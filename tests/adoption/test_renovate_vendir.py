from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path
from types import SimpleNamespace

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
    assert "dir" not in task
    assert task["run"] == "uv run python tests/adoption/run_renovate_probe.py"


def test_probe_runner_uses_exact_renovate_command_and_propagates_status() -> None:
    path = Path(__file__).with_name("run_renovate_probe.py")
    spec = importlib.util.spec_from_file_location("run_renovate_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def run(argv: list[str], *, cwd: Path, timeout: int, check: bool) -> SimpleNamespace:
        calls.append((argv, cwd, timeout, check))
        return SimpleNamespace(returncode=7)

    assert module.main(run=run) == 7
    assert calls == [
        (
            [
                "npx",
                "--yes",
                "renovate@43.285.7",
                "--platform=local",
                "--dry-run=full",
                "--require-config=required",
                "--binary-source=global",
                "--base-dir=/tmp/dotagents-renovate-vendir-probe",
            ],
            FIXTURE,
            120,
            False,
        )
    ]
