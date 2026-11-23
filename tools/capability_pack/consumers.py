"""The repositories a release bumps (`cli consumer-matrix`). Standard library only, so the consumer sync's plan job
runs it on the runner's own python3, before any tool is installed."""

from __future__ import annotations

import json
import os
import re
import sys


class ConsumerListError(ValueError):
    pass


REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$")
QUEUES = ("mergify", "auto-merge", "none")


def consumer_matrix(own: str, raw: str | None) -> list[dict[str, str]]:
    """The repositories a release bumps: this one (`own`, landed through its Mergify queue) first, then each entry of
    `raw`, the owner's `ENGINEERING_CONSUMERS` variable: a JSON list whose items are `owner/repo` (GitHub auto-merge)
    or `{"repository": "owner/repo", "queue": "auto-merge" | "mergify" | "none"}`. Unset or blank means this repo
    only, so no consumer name ever lives in this public repo; a malformed variable is refused, never half-read."""
    entries: list[dict[str, str]] = [{"repository": own, "queue": "mergify"}]
    if raw is None or not raw.strip():
        return entries
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConsumerListError(f"ENGINEERING_CONSUMERS is no JSON list: {error}") from None
    if not isinstance(items, list):
        raise ConsumerListError("ENGINEERING_CONSUMERS must be a JSON list")
    for item in items:
        entry = {"repository": item, "queue": "auto-merge"} if isinstance(item, str) else item
        if not isinstance(entry, dict) or set(entry) - {"repository", "queue"}:
            raise ConsumerListError(
                f"ENGINEERING_CONSUMERS entry is not owner/repo or {{repository, queue}}: {item!r}"
            )
        repository, queue = entry.get("repository"), entry.get("queue", "auto-merge")
        if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
            raise ConsumerListError(f"ENGINEERING_CONSUMERS entry names no owner/repo: {item!r}")
        if queue not in QUEUES:
            raise ConsumerListError(
                f"ENGINEERING_CONSUMERS queue must be one of {', '.join(QUEUES)}: {item!r}"
            )
        if repository.lower() in {e["repository"].lower() for e in entries}:
            continue
        entries.append({"repository": repository, "queue": queue})
    return entries


if __name__ == "__main__":
    try:
        print(json.dumps(consumer_matrix(sys.argv[1], os.environ.get("ENGINEERING_CONSUMERS"))))
    except ConsumerListError as error:
        print(error, file=sys.stderr)
        sys.exit(4)
