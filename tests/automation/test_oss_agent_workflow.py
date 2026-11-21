"""oss-agent.yml keeps its two powers apart and talks to nothing but GitHub and the model (#1647)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
FILES = ("oss-agent.yml", "oss-agent-selftest.yml")
MODEL_KEY = "NVIDIA_NIM_API_KEY"


def _load(name: str) -> dict:
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


WORKFLOW = _load("oss-agent.yml")
AGENT = WORKFLOW["jobs"]["agent"]
PUBLISH = WORKFLOW["jobs"]["publish"]


def _runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_nothing_reaches_a_host_a_tailnet_or_omnigent() -> None:
    for name in FILES:
        text = (WORKFLOWS / name).read_text()
        for pattern in (r"omnigent", r"tailscale", r"tailnet", r"\bts_", r"ssh", r"RUNNER_SERVER"):
            assert not re.search(pattern, text, re.IGNORECASE), (name, pattern)
        # the one secret is the model key, and it goes nowhere else
        assert set(re.findall(r"secrets\.(\w+)", text)) <= {MODEL_KEY}, name
    assert set(WORKFLOW["on"]["workflow_call"]["secrets"]) == {MODEL_KEY}


def test_every_action_is_pinned_to_a_commit() -> None:
    for name in FILES:
        for job in _load(name)["jobs"].values():
            for step in job.get("steps", []):
                if "uses" in step:
                    assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", step["uses"]), step


def test_no_input_is_interpolated_into_a_script() -> None:
    # a task is untrusted text: it reaches a shell only through an env var
    for job in WORKFLOW["jobs"].values():
        for step in job["steps"]:
            assert "${{" not in step.get("run", ""), step


def test_agent_job_reads_only_and_proves_it_cannot_push() -> None:
    assert AGENT["permissions"] == {"contents": "read"}
    assert WORKFLOW["permissions"] == {}
    probe = next(step for step in AGENT["steps"] if step.get("id") == "push-refused")
    assert "git push" in probe["run"]
    assert "exit 1" in probe["run"].split("then", 1)[1].split("fi", 1)[0]
    # the checkout leaves no credential behind for the agent
    checkout = AGENT["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["persist-credentials"] == "false"


def test_a_failing_command_in_a_pipe_fails_its_step() -> None:
    # an explicit `bash` runs with -o pipefail; GitHub's default `bash -e` does not
    assert WORKFLOW["defaults"]["run"]["shell"] == "bash"
    for job in WORKFLOW["jobs"].values():
        for step in job["steps"]:
            assert "shell" not in step, step


def test_agent_job_has_a_time_limit() -> None:
    assert AGENT["timeout-minutes"] == "${{ inputs.timeout_minutes }}"
    assert int(WORKFLOW["on"]["workflow_call"]["inputs"]["timeout_minutes"]["default"]) > 0


def test_model_key_reaches_only_the_proxy_step() -> None:
    holders = [
        step.get("name")
        for job in WORKFLOW["jobs"].values()
        for step in job["steps"]
        if MODEL_KEY in str(step)
    ]
    assert holders == ["Start the FCC proxy"]
    assert MODEL_KEY not in str(PUBLISH)


def test_publish_job_runs_nothing_from_the_patch() -> None:
    assert PUBLISH["permissions"] == {"contents": "write", "pull-requests": "write"}
    assert "secrets" not in str(PUBLISH)
    assert [step["uses"].split("@")[0] for step in PUBLISH["steps"] if "uses" in step] == [
        "actions/checkout",
        "actions/download-artifact",
    ]
    runs = _runs(PUBLISH)
    commands = {
        line.strip().split()[0]
        for line in runs.splitlines()
        if line.strip() and not line.strip().startswith(("{", "}", "echo", "title=", "url="))
    }
    assert commands <= {"git"}, commands
    patch_lines = [line.strip() for line in runs.splitlines() if "patch" in line]
    assert patch_lines == ['git am "$RUNNER_TEMP/patch/agent.patch"']
    # nothing executes from the checkout: no interpreter, build tool or path
    assert not re.search(r"\b(bash|sh|source|make|npm|npx|uv|python3?|node)\b|\./", runs)


def test_selftest_runs_the_dry_run_only() -> None:
    selftest = _load("oss-agent-selftest.yml")
    job = selftest["jobs"]["dry-run"]
    assert job["uses"] == "./.github/workflows/oss-agent.yml"
    assert job["with"]["dry_run"] == "true"
    assert "secrets" not in job
