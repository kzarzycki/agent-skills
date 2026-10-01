#!/usr/bin/env python3
"""Spec gate (engineering-loop landing): a PR lands only when every issue it closes is specced and categorised.

Two labels are an issue's state: neither is an intent that needs triage, `needs-owner` waits for the owner, and
`ready-for-agent` means a spec was written into it; others only classify (the skill's issues.md). A PR
that closes no issue, or closes one that isn't `ready-for-agent`, skipped the spec state; one without exactly one
category, a component and exactly one size can't be filtered or weighed. A `wayfinder:` ticket needs only its state:
it settles a decision, and that label is its category. A soft gate against a forgotten state, not a security
boundary: any agent can add the label.

    python3 scripts/spec_gate.py <pr>

Run from the repo root. The components, and any categories beyond the method's four, are the first backticked name of
each list item under `## Components` and `## Extra categories` in docs/agents/issue-tracker.md. Reads the PR's closing
issues and their labels through `gh`. Exit 1 with one line per problem. The closing issues are GitHub's closing
references (a `Closes #n` line it linked, or a link made in the sidebar) plus every `#n` after a closing keyword in the
PR body: GitHub sometimes never links such a line, and has no API to set the link. Stdlib only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

READY = "ready-for-agent"
CATEGORIES = {"bug", "enhancement", "documentation", "chore"}
SIZES = {"size:XS", "size:S", "size:M", "size:L", "size:XL"}
TRACKER = Path("docs/agents/issue-tracker.md")
ISSUE = "number labels(first: 50) { nodes { name } }"
QUERY = f"""query($owner: String!, $name: String!, $pr: Int!) {{
  repository(owner: $owner, name: $name) {{
    pullRequest(number: $pr) {{ body closingIssuesReferences(first: 50) {{ nodes {{ {ISSUE} }} }} }}
  }}
}}"""
# GitHub's closing keywords; ponytail: same-repo `#n` only, add owner/repo#n and issue URLs when a PR here uses one.
CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?[ \t]+#(\d+)\b", re.IGNORECASE)
# code and comments: an example, not a closing line
QUOTED = re.compile(r"^[ \t>]*```.*?^[ \t>]*```|`[^`\n]*`|<!--.*?-->", re.DOTALL | re.MULTILINE)


def named(body: str) -> list[int]:
    """The issue numbers a PR body names after a closing keyword on the same line, in order, each once."""
    return list(dict.fromkeys(int(number) for number in CLOSING.findall(QUOTED.sub("", body))))


def listed(tracker: str, heading: str) -> set[str]:
    """The first backticked name of each list item under `## <heading>`, up to the next `## ` heading."""
    section = re.search(
        rf"^## {re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", tracker, re.DOTALL | re.MULTILINE
    )
    return (
        set(re.findall(r"^[ \t]*[-*] [^`\n]*`([^`\n]+)`", section.group(1), re.MULTILINE))
        if section
        else set()
    )


def problems(
    issues: list[dict[str, Any]], components: set[str], categories: set[str] = CATEGORIES
) -> list[str]:
    """One line per reason the PR skipped the spec state; empty when it may land."""
    if not issues:
        return [
            "the PR closes no issue: it needs a `Closes #<spec>` line for a ready-for-agent spec"
        ]
    found = []
    for issue in issues:
        labels = {label["name"] for label in issue["labels"]["nodes"]}
        if READY not in labels:
            found.append(f"#{issue['number']} is not {READY}: triage and spec it first")
        if any(label.startswith("wayfinder:") for label in labels):
            continue  # a wayfinder ticket settles a decision: its wayfinder: label is its category, and it has no component or size
        for kind, names in (("category", categories), ("size", SIZES)):
            if len(labels & names) != 1:
                found.append(
                    f"#{issue['number']} needs exactly one {kind} label ({', '.join(sorted(names))}), has {len(labels & names)}"
                )
        if not labels & components:
            found.append(
                f"#{issue['number']} needs a component label ({', '.join(sorted(components)) or f'{TRACKER} lists none'})"
            )
    return found


def _graphql(query: str, **fields: object) -> Any:
    args = [arg for key, value in fields.items() for arg in ("-F", f"{key}={value}")]
    out = subprocess.run(  # gh fills {owner} and {repo} from the current checkout
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            "owner={owner}",
            "-F",
            "name={repo}",
            *args,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)["data"]["repository"]


def closing_issues(pr: int) -> list[dict[str, Any]]:
    pull = _graphql(QUERY, pr=pr)["pullRequest"]
    issues: list[dict[str, Any]] = pull["closingIssuesReferences"]["nodes"]
    unlinked = sorted(set(named(pull["body"])) - {issue["number"] for issue in issues})
    if unlinked:  # a `#n` that is a pull request comes back empty and is dropped
        aliases = " ".join(
            f"i{n}: issueOrPullRequest(number: {n}) {{ ... on Issue {{ {ISSUE} }} }}"
            for n in unlinked
        )
        found = _graphql(
            f"query($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"
        )
        issues = issues + [issue for issue in found.values() if issue]
    return issues


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not argv[0].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    try:
        tracker = TRACKER.read_text()
    except OSError as exc:
        print(f"{TRACKER}: {exc.strerror}: run from the repo root")
        return 1
    try:
        found = problems(
            closing_issues(int(argv[0])),
            listed(tracker, "Components"),
            CATEGORIES | listed(tracker, "Extra categories"),
        )
    except subprocess.CalledProcessError as exc:
        # gh's reason, e.g. a closing line that names a number with no issue
        print(exc.stderr.strip() or exc)
        return 1
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
