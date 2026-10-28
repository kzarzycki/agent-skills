#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Split manifest to issue batch (engineering loop): validate a split manifest and print the canonical batch.

    uv run scripts/issue_batch.py github MANIFEST [--label NAME]... > batch.json
    uv run scripts/issue_batch.py local MANIFEST [--out DIR] [--status NAME]

Both read the manifest of docs/layers.md, Split manifest, and refuse it before anything is written: an
unreadable file, a `version` other than 1, a missing or non-string field, a duplicate title, a blocker that
names no item, or a cycle. Exit 1 with the reason.

- `github` prints the batch github.md, Publish an issue batch, publishes: `batch_sha256` and each issue's
  `title`, `body` (the item's `spec` byte-for-byte), `labels`, `blockers` and `order`, plus its `marker` and
  `marked_body`, and the blocking `relationships`. `--label` repeats and is the one label list for every issue
  (the caller's label map); with none it is `ready-for-agent`, the label the tickets always carried.
- `local` writes one file per item, `<DIR>/<NN>-<slug>.md`, numbered from 01 in dependency order, in the local
  ticket template, and prints each path. `--out` defaults to `issues/` beside the manifest; `--status` is the
  Status line (default `ready-for-agent`). The spec's `## What to build`, `## Acceptance criteria` and
  `## Blocked by` sections fill the template; a spec without them becomes the "What to build" text.

Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->"
DEFAULT_LABEL = "ready-for-agent"


class BatchError(ValueError):
    pass


def tickets_from_manifest(path: Path, labels: list[str]) -> list[dict]:
    """The manifest's items as tickets (`body`, `labels`, `blockers`), validated."""
    try:
        manifest = json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise BatchError(f"unreadable manifest {path}: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise BatchError("manifest version must be 1")
    items = manifest.get("items")
    if not isinstance(items, list):
        raise BatchError("manifest items must be a list")
    tickets = []
    for item in items:
        if not isinstance(item, dict):
            raise BatchError("every item must be an object")
        blocked_by = item.get("blocked_by")
        if (
            not isinstance(item.get("title"), str)
            or not isinstance(item.get("spec"), str)
            or not isinstance(blocked_by, list)
            or not all(isinstance(title, str) for title in blocked_by)
        ):
            raise BatchError("every item needs a string title, a string spec and a blocked_by list")
        tickets.append(
            {"title": item["title"], "body": item["spec"], "labels": labels, "blockers": blocked_by}
        )
    order(tickets)
    return tickets


def order(tickets: list[dict]) -> list[dict]:
    """Stable topological order: of the tickets whose blockers are ordered, the smallest UTF-8 title first."""
    by_title = {ticket["title"]: ticket for ticket in tickets}
    if len(by_title) != len(tickets):
        raise BatchError("ticket titles must be unique")
    for ticket in tickets:
        unknown = set(ticket["blockers"]) - by_title.keys()
        if unknown:
            raise BatchError(f"{ticket['title']!r} is blocked by unknown {sorted(unknown)}")
    remaining = set(by_title)
    ordered: list[dict] = []
    while remaining:
        ready = [
            by_title[title]
            for title in remaining
            if not set(by_title[title]["blockers"]) & remaining
        ]
        if not ready:
            raise BatchError("ticket blockers must form an acyclic graph")
        selected = min(ready, key=lambda ticket: ticket["title"].encode("utf-8"))
        ordered.append(selected)
        remaining.remove(selected["title"])
    return ordered


def prepare(tickets: list[dict]) -> dict:
    """The canonical batch: `batch_sha256`, `issues` (marked) and `relationships`."""
    ordered = order(tickets)
    order_by_title = {ticket["title"]: n for n, ticket in enumerate(ordered, start=1)}
    canonical = [
        {
            "title": ticket["title"],
            "body": ticket["body"],
            "labels": sorted(set(ticket["labels"])),
            "blockers": sorted(set(ticket["blockers"]), key=order_by_title.__getitem__),
            "order": order_by_title[ticket["title"]],
        }
        for ticket in ordered
    ]
    canonical_bytes = json.dumps(
        canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()
    batch_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    issues = []
    for ticket in canonical:
        marker = MARKER.format(batch_sha256=batch_sha256, ordinal=ticket["order"])
        issues.append(
            {
                **ticket,
                "marker": marker,
                "marked_body": f"{ticket['body']}\n\n{marker}",
                "url": None,
            }
        )
    relationships = [
        {
            "blocked_order": issue["order"],
            "blocker_order": order_by_title[blocker],
            "status": "pending",
        }
        for issue in issues
        for blocker in issue["blockers"]
    ]
    return {"batch_sha256": batch_sha256, "issues": issues, "relationships": relationships}


def _section(spec: str, heading: str) -> str | None:
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", spec, re.DOTALL | re.MULTILINE
    )
    return match.group(1).strip() if match else None


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "ticket"


def local_files(tickets: list[dict], status: str) -> dict[str, str]:
    """File name -> content, one per ticket in dependency order, in the local ticket template."""
    ordered = order(tickets)
    number = {ticket["title"]: f"{n:02d}" for n, ticket in enumerate(ordered, start=1)}
    files = {}
    for ticket in ordered:
        spec = ticket["body"]
        build = _section(spec, "What to build") or spec.strip()
        criteria = _section(spec, "Acceptance criteria")
        blockers = ", ".join(
            f"{number[title]} {title}"
            for title in sorted(ticket["blockers"], key=number.__getitem__)
        )
        content = (
            f"# {number[ticket['title']]}: {ticket['title']}\n\n"
            f"**What to build:** {build}\n\n"
            f"**Blocked by:** {blockers or 'None (can start immediately)'}\n\n"
            f"**Status:** {status}\n"
        )
        if criteria:
            content += f"\n{criteria}\n"
        files[f"{number[ticket['title']]}-{_slug(ticket['title'])}.md"] = content
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="target", required=True)
    github = sub.add_parser("github")
    github.add_argument("manifest", type=Path)
    github.add_argument("--label", action="append", default=[])
    local = sub.add_parser("local")
    local.add_argument("manifest", type=Path)
    local.add_argument("--out", type=Path)
    local.add_argument("--status", default=DEFAULT_LABEL)
    args = parser.parse_args(argv)
    try:
        if args.target == "github":
            tickets = tickets_from_manifest(args.manifest, args.label or [DEFAULT_LABEL])
            print(json.dumps(prepare(tickets), ensure_ascii=False, indent=2))
        else:
            tickets = tickets_from_manifest(args.manifest, [])
            out = args.out or args.manifest.parent / "issues"
            out.mkdir(parents=True, exist_ok=True)
            for name, content in local_files(tickets, args.status).items():
                (out / name).write_text(content)
                print(out / name)
    except BatchError as error:
        print(f"issue_batch.py: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
