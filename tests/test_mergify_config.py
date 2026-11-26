"""`.mergify.yml`: the Mergify merge queue `land.queue: mergify` hands PRs to (#1658), and the CI split that runs the
tests once per tree, on the batch (#1821).

`land` posts the `land` status on a landable PR's head and adds `loop:queued`; Mergify must take a PR in only with
both, squash it, retry a red batch once, split a batch still red until only the failing PR leaves, and mark a PR it
drops with `loop:dequeued`, which `land` evicts. The base's required CI checks are no line here: Mergify reads them
from the base's rules, so the file stays repo-neutral: the pack's template rendered with gatekeeper.md's `land`
batching (`approvals.py queue-config`), and a batch merges only on the `queue-run` job (R6's refusal).
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "gatekeeper" / "skills" / "gatekeeper" / "mergify.yml"
sys.path.insert(0, str(TEMPLATE.parent / "scripts"))
import approvals

HANDED_OVER = [
    "base = main",
    "-draft",
    "label = loop:queued",
    "-label = loop:solo",
    "-label = loop:hold",
    "check-success = land",
]


def named(rules: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """The one rule called `name`: the default queue rule beside the whole-suite `solo` one (#2553)."""
    [found] = [rule for rule in rules if rule["name"] == name]
    return found


def config() -> dict[str, Any]:
    found: dict[str, Any] = yaml.safe_load((ROOT / ".mergify.yml").read_text())
    return found


def qualify() -> dict[str, Any]:
    """engineering-ci.yml's `qualify` job, the check main requires."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "engineering-ci.yml").read_text())
    job: dict[str, Any] = workflow["jobs"]["qualify"]
    return job


def runs(command: str) -> list[dict[str, Any]]:
    """The `qualify` steps whose `run` is `command`."""
    return [step for step in qualify()["steps"] if step.get("run") == command]


def policy() -> dict[str, Any]:
    """gatekeeper.md's `## Policy` block."""
    text = (ROOT / "docs" / "agents" / "gatekeeper.md").read_text()
    block = re.search(r"## Policy\n\n```yaml\n(.*?)```", text, re.DOTALL)
    assert block, "gatekeeper.md has no Policy block"
    found: dict[str, Any] = yaml.safe_load(block[1])
    return found


def test_one_squash_queue_takes_in_only_what_land_handed_over() -> None:
    """Its conditions are exactly land's hand-over: no CI check, which the base's rules give Mergify."""
    rule = named(config()["queue_rules"], "default")
    assert rule["merge_method"] == "squash"
    assert rule["queue_conditions"] == HANDED_OVER
    assert "check-success" not in " ".join(rule["queue_conditions"]).replace(
        "check-success = land", ""
    )


def test_a_red_batch_is_retried_once_and_a_dropped_pr_labelled_for_eviction() -> None:
    rule = named(config()["queue_rules"], "default")
    assert rule["max_checks_retries"] == 1
    assert config()["merge_queue"]["dequeued_label"] == "loop:dequeued"


def test_a_red_batch_is_split_until_only_the_failing_pr_leaves() -> None:
    """`null` is Mergify's no-cap: it splits the batch as many rounds as it takes, so the culprit alone is dequeued; a
    number would dequeue a part still holding several PRs, and 0 the whole batch. The key is set on purpose, never
    left to the default."""
    rule = named(config()["queue_rules"], "default")
    assert "batch_max_failure_resolution_attempts" in rule
    assert rule["batch_max_failure_resolution_attempts"] is None


def test_every_batch_is_tested_on_a_draft_pr_from_the_prefix_ci_tests() -> None:
    """The prefix is the one the test step matches."""
    rule = named(config()["queue_rules"], "default")
    assert rule["max_checks_retries"] >= 1
    [tests] = runs("mise run test-batch")
    # but not on a rerun attempt that read the red attempt's failed tests: rerun-tests runs the selection then (R5, #1794)
    assert tests["if"] == (
        f"startsWith(github.head_ref, '{rule['queue_branch_prefix']}')"
        " && steps.read.outputs.red != 'read'"
    )


def test_the_queue_never_checks_a_pr_in_place() -> None:
    """#2157: Mergify checks a PR on its own branch, where `qualify` runs no tests, unless its CI is two-step. It
    computes that (`allow_inplace_checks` is deprecated), so the one key that forbids it is `merge_conditions` that
    are not empty and differ from `queue_conditions`; set the setting back and #2151 and #2134 merge untested again."""
    rule = named(config()["queue_rules"], "default")
    assert rule.get("allow_inplace_checks") is not True
    assert rule["merge_conditions"], (
        "empty merge_conditions are single-step: Mergify may check in place"
    )
    assert rule["merge_conditions"] != rule["queue_conditions"]
    assert rule["merge_method"] != "merge-batch"


def test_a_pr_head_runs_only_cheap_checks_and_the_batch_runs_the_tests() -> None:
    """The job has no `if`, so `qualify` reports on every PR (a skipped required check never does, #394); the cheap
    check runs on every PR and push, and the only step that runs pytest is the batch's (and the owner's dispatch)."""
    job = qualify()
    assert "if" not in job
    [cheap] = runs("mise run check-fast")
    assert cheap["if"] == (
        "github.event_name != 'schedule' && github.event_name != 'workflow_dispatch'"
        " && steps.tested.outputs.skip != 'true' && steps.record.outputs.recorded != 'true'"
    )
    tasks = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]
    assert (
        "pytest" not in tasks["check-fast"]["run"]
        and "mise run test" not in tasks["check-fast"]["run"]
    )
    assert "pytest" in tasks["test-batch"]["run"]
    testing = [
        step
        for step in job["steps"]
        if "pytest" in step.get("run", "")
        or "approvals.py rerun-tests" in step.get("run", "")
        or step.get("run") in ("mise run test-batch", "mise run check")
    ]
    assert [step["if"] for step in testing] == [
        "startsWith(github.head_ref, 'mergify/merge-queue/') && steps.read.outputs.red != 'read'",
        "steps.read.outputs.red == 'read'",
        "github.event_name == 'workflow_dispatch' && inputs.tests != ''",
        "github.event_name == 'schedule' && steps.tested.outputs.skip != 'true'",
    ]


def rendered(land: str) -> dict[str, Any]:
    """queue-config's Mergify config for a gatekeeper.md whose `land` block holds `land`."""
    policy = approvals.Policy(f"## Policy\n\n```yaml\nland:\n  queue: mergify\n{land}```\n")
    found: dict[str, Any] = yaml.safe_load(approvals.queue_config(policy))
    return found


def test_the_batch_size_and_wait_in_land_reach_the_rendered_config() -> None:
    """#2178: batching is the project's `land` config; `batch_size: 1` is one PR per entry."""
    rule = named(rendered("  batch_size: 1\n  batch_wait_seconds: 90\n")["queue_rules"], "default")
    assert (rule["batch_size"], rule["batch_max_wait_time"]) == (1, "90 seconds")
    rule = named(
        rendered("  batch_size: 5\n  batch_wait_seconds: 3600\n")["queue_rules"], "default"
    )
    assert (rule["batch_size"], rule["batch_max_wait_time"]) == (5, "1 hour")


def test_a_land_block_without_the_keys_keeps_the_templates_batching() -> None:
    rule = named(rendered("")["queue_rules"], "default")
    template = named(yaml.safe_load(TEMPLATE.read_text())["queue_rules"], "default")
    assert (rule["batch_size"], rule["batch_max_wait_time"]) == (
        template["batch_size"],
        template["batch_max_wait_time"],
    )


def test_a_batch_size_under_one_is_refused() -> None:
    with pytest.raises(approvals.Refused, match="land.batch_size"):
        rendered("  batch_size: 0\n")


def test_the_repo_file_is_the_rendered_template_and_the_head_check_catches_drift() -> None:
    """The repo commits queue-config's output, so any difference is drift; check-fast fails on it on every PR head."""
    policy = approvals.Policy((ROOT / "docs" / "agents" / "gatekeeper.md").read_text())
    assert (ROOT / ".mergify.yml").read_text() == approvals.queue_config(policy)
    cheap = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["check-fast"]["run"]
    assert "approvals.py queue-config | cmp - .mergify.yml" in cheap


def test_the_rendered_queue_timeout_follows_timeouts_run() -> None:
    """#2228: `checks_timeout` is `timeouts.run`; this repo's block says 60m (#2232), the template's 1 hour."""
    assert policy()["timeouts"] == {"test": "60s", "run": "60m"}
    rule = named(config()["queue_rules"], "default")
    assert rule["checks_timeout"] == "1 hour"
    policy_text = approvals.Policy(
        "## Policy\n\n```yaml\nland:\n  queue: mergify\ntimeouts:\n  run: 4h\n```\n"
    )
    rendered_rule = named(
        yaml.safe_load(approvals.queue_config(policy_text))["queue_rules"], "default"
    )
    assert rendered_rule["checks_timeout"] == "4 hours"


def test_a_batch_merges_only_once_its_test_step_ran_its_selection() -> None:
    """R6's refusal (#2169, #2121): `queue-run`, the one merge condition beside `-conflict`, runs only on a batch
    branch after `qualify` and passes only on the output the step after the batch's test step sets once it passed."""
    rule = named(config()["queue_rules"], "default")
    assert rule["merge_conditions"] == ["-conflict", "check-success = queue-run"]
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "engineering-ci.yml").read_text())
    job = workflow["jobs"]["queue-run"]
    assert job["needs"] == "qualify"
    assert job["if"] == f"startsWith(github.head_ref, '{rule['queue_branch_prefix']}')"
    [step] = job["steps"]
    assert step["env"]["SELECTION"] == "${{ needs.qualify.outputs.selection }}"
    assert qualify()["outputs"]["selection"] == "${{ steps.selection.outputs.selection }}"
    [batch] = [s for s in qualify()["steps"] if s.get("id") == "batch"]
    assert batch["run"] == "mise run test-batch"
    [ran] = [s for s in qualify()["steps"] if s.get("id") == "selection"]
    assert ran["if"] == "steps.batch.outcome == 'success' || steps.rerun.outcome == 'success'"
    assert ran["run"] == 'echo selection=ran >> "$GITHUB_OUTPUT"'


def test_batches_of_three_wait_five_minutes_and_a_silent_check_times_out() -> None:
    """The spec's batch values, and a timeout so a check that never reports can't hold the queue."""
    rule = named(config()["queue_rules"], "default")
    assert (rule["batch_size"], rule["batch_max_wait_time"], rule["checks_timeout"]) == (
        3,
        "5 minutes",
        "1 hour",
    )


def test_the_queue_action_fires_on_the_same_conditions() -> None:
    """Mergify queues a PR only through an action, here on exactly land's hand-over."""
    rule = named(config()["pull_request_rules"], "queue what land handed over")
    assert rule["actions"] == {"queue": {"name": "default"}}
    assert rule["conditions"] == HANDED_OVER


def test_the_policy_names_mergify_as_mains_queue() -> None:
    """The switch that sends this repo's landings to Mergify instead of the host batch gate, and its batching."""
    assert policy()["land"]["queue"] == "mergify"
    assert (policy()["land"]["batch_size"], policy()["land"]["batch_wait_seconds"]) == (3, 300)


def test_the_queue_only_variant_keeps_an_ungated_lint_job() -> None:
    """#2687: a gate that runs only in the queue leaves a PR push with no check, so a lint failure first shows in the
    queue and evicts the PR. The variant's CI has a `lint` job with no job-level `if`, which runs lint-only, and a
    gate that stays gated to the queue's draft PRs."""
    workflow = yaml.safe_load((TEMPLATE.parent / "queue-only-ci.yml").read_text())
    jobs = workflow["jobs"]
    assert "if" not in jobs["lint"]
    assert "pull_request" in workflow[True]
    commands = " ".join(step.get("run", "") for step in jobs["lint"]["steps"])
    assert "lint" in commands and "test" not in commands and "build" not in commands
    assert jobs["gate"]["if"] == "startsWith(github.head_ref, 'mergify/merge-queue/')"
    assert "`lint` job" in TEMPLATE.read_text()


def test_the_pack_ci_lints_every_pr_push_and_the_lint_task_runs_no_test() -> None:
    """#2687: engineering-ci.yml follows the same rule: a `lint` job with no record read, on pull requests."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "engineering-ci.yml").read_text())
    job = workflow["jobs"]["lint"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert [step["run"] for step in job["steps"] if "lint" in step.get("run", "")] == [
        "mise run lint-changed"
    ]
    assert all("pr_head_record" not in step.get("run", "") for step in job["steps"])
    task = tomllib.loads((ROOT / "mise.toml").read_text())["tasks"]["lint-changed"]["run"]
    assert "ruff check" in task and "pytest" not in task and "build" not in task
