"""`.mergify.yml`: the Mergify merge queue `land.queue: mergify` hands PRs to (#1658).

`land` posts the `land` status on a landable PR's head and adds `loop:queued`; Mergify must take a PR in only with
both, squash it, retry a red batch once and mark a PR it drops with `loop:dequeued`, which `land` evicts. The base's
required CI checks are no line here: Mergify reads them from the base's rules, so the file stays repo-neutral.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
HANDED_OVER = {"base = main", "-draft", "label = loop:queued", "check-success = land"}


def config() -> dict[str, Any]:
    found: dict[str, Any] = yaml.safe_load((ROOT / ".mergify.yml").read_text())
    return found


def test_mergify_config_conditions() -> None:
    """One squash queue whose conditions require `loop:queued` and `land`, retrying a red batch once."""
    [rule] = config()["queue_rules"]
    assert rule["merge_method"] == "squash"
    assert rule["max_checks_retries"] == 1
    assert HANDED_OVER <= set(rule["queue_conditions"])
    assert config()["merge_queue"]["dequeued_label"] == "loop:dequeued"


def test_the_queue_action_takes_in_only_what_land_handed_over() -> None:
    """Mergify queues a PR only through a `queue` action, on the same conditions."""
    [rule] = config()["pull_request_rules"]
    assert "queue" in rule["actions"]
    assert HANDED_OVER <= set(rule["conditions"])


def test_no_ci_check_is_named_so_the_file_suits_any_repo() -> None:
    """The required CI check comes from the base's rules, which Mergify injects, never from this file."""
    text = (ROOT / ".mergify.yml").read_text()
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    assert not any("qualify" in line for line in lines)
