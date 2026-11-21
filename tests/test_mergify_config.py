"""`.mergify.yml`: the Mergify merge queue `land.queue: mergify` hands PRs to (#1658).

`land` posts the `land` status on a landable PR's head and adds `loop:queued`; Mergify must take a PR in only with
both, squash it, retry a red batch once and mark a PR it drops with `loop:dequeued`, which `land` evicts. The base's
required CI checks are no line here: Mergify reads them from the base's rules, so the file stays repo-neutral.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
HANDED_OVER = ["base = main", "-draft", "label = loop:queued", "check-success = land"]


def config() -> dict[str, Any]:
    found: dict[str, Any] = yaml.safe_load((ROOT / ".mergify.yml").read_text())
    return found


def policy() -> dict[str, Any]:
    """gatekeeper.md's `## Policy` block."""
    text = (ROOT / "docs" / "agents" / "gatekeeper.md").read_text()
    block = re.search(r"## Policy\n\n```yaml\n(.*?)```", text, re.DOTALL)
    assert block, "gatekeeper.md has no Policy block"
    found: dict[str, Any] = yaml.safe_load(block[1])
    return found


def test_one_squash_queue_takes_in_only_what_land_handed_over() -> None:
    """Its conditions are exactly land's hand-over: no CI check, which the base's rules give Mergify."""
    [rule] = config()["queue_rules"]
    assert rule["merge_method"] == "squash"
    assert rule["queue_conditions"] == HANDED_OVER
    assert "merge_conditions" not in rule


def test_a_red_batch_is_retried_once_and_a_dropped_pr_labelled_for_eviction() -> None:
    [rule] = config()["queue_rules"]
    assert rule["max_checks_retries"] == 1
    assert config()["merge_queue"]["dequeued_label"] == "loop:dequeued"


def test_batches_of_three_wait_five_minutes_and_a_silent_check_times_out() -> None:
    """The spec's batch values, and a timeout so a check that never reports can't hold the queue."""
    [rule] = config()["queue_rules"]
    assert (rule["batch_size"], rule["batch_max_wait_time"], rule["checks_timeout"]) == (
        3,
        "5 minutes",
        "1 hour",
    )


def test_the_queue_action_fires_on_the_same_conditions() -> None:
    """Mergify queues a PR only through an action, here on exactly land's hand-over."""
    [rule] = config()["pull_request_rules"]
    assert rule["actions"] == {"queue": {"name": "default"}}
    assert rule["conditions"] == HANDED_OVER


def test_the_policy_names_mergify_as_mains_queue() -> None:
    """The switch that sends this repo's landings to Mergify instead of the host batch gate."""
    assert policy()["land"]["queue"] == "mergify"
