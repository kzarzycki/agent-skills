#!/usr/bin/env python3
"""Board move (engineering loop): put an issue in a column of the repo's project board.

    python3 scripts/board.py <issue> <column>
    python3 scripts/board.py column <issue>

The columns are the loop's stages (the skill's issues.md). Adds the issue to the board when it is not there yet,
then sets its Status. Ids are looked up by name on every call: GitHub changes option ids whenever a field is edited.
Exit 1 with gh's reason or the valid columns; the labels, not the board, are an issue's state, so a failed move never
blocks a ticket. Needs the `project` token scope (`gh auth refresh -s project`).

`column` prints the issue's column, or nothing when the repo has no board or the issue is not on it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

# ponytail: the repo's first linked project is the board; pick by title when a second one is linked.
LOOKUP = """query($owner: String!, $name: String!, $issue: Int!) {
  repository(owner: $owner, name: $name) {
    issue(number: $issue) { id }
    projectsV2(first: 1) { nodes { id field(name: "Status") { ... on ProjectV2SingleSelectField { id options { id name } } } } }
  }
}"""
ADD = """mutation($project: ID!, $issue: ID!) {
  addProjectV2ItemById(input: {projectId: $project, contentId: $issue}) { item { id } }
}"""
COLUMN = """query($owner: String!, $name: String!, $issue: Int!) {
  repository(owner: $owner, name: $name) {
    projectsV2(first: 1) { nodes { id } }
    issue(number: $issue) { projectItems(first: 20) { nodes { project { id } fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } } } } }
  }
}"""
SET = """mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {projectId: $project, itemId: $item, fieldId: $field, value: {singleSelectOptionId: $option}}) { projectV2Item { id } }
}"""


def target(projects: list[dict[str, Any]], column: str) -> tuple[str, str, str]:
    """The board's project id, its Status field id and the column's option id."""
    if not projects:
        raise ValueError("no project board is linked to this repo")
    project = projects[0]
    options = {
        option["name"]: option["id"] for option in (project["field"] or {}).get("options", [])
    }
    if column not in options:
        raise ValueError(
            f"no column {column!r}: the board has {', '.join(options) or 'no Status field'}"
        )
    return project["id"], project["field"]["id"], options[column]


def fields(**values: int | str) -> list[str]:
    """gh's field flags: -F for a number or a {placeholder} gh fills, -f for an id, which -F would turn into a number when it is all digits."""
    return [
        arg
        for key, value in values.items()
        for arg in (
            "-F" if isinstance(value, int) or value.startswith("{") else "-f",
            f"{key}={value}",
        )
    ]


def _graphql(query: str, **values: int | str) -> Any:
    out = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}", *fields(**values)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)["data"]


def move(issue: int, column: str) -> None:
    # gh fills owner and repo from the checkout
    repo = _graphql(LOOKUP, owner="{owner}", name="{repo}", issue=issue)["repository"]
    project, field, option = target(repo["projectsV2"]["nodes"], column)
    # the existing item when already there
    added = _graphql(ADD, project=project, issue=repo["issue"]["id"])["addProjectV2ItemById"]
    item = added["item"]["id"]
    _graphql(SET, project=project, item=item, field=field, option=option)


def column_of(repo: dict[str, Any]) -> str:
    """The issue's Status on the repo's board; empty without a board, off it, or with no Status."""
    boards = repo["projectsV2"]["nodes"]
    if not boards:
        return ""
    for item in repo["issue"]["projectItems"]["nodes"]:
        if item["project"]["id"] == boards[0]["id"]:
            return (item["fieldValueByName"] or {}).get("name", "")
    return ""


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "column" and argv[1].isdigit():
        try:
            repo = _graphql(COLUMN, owner="{owner}", name="{repo}", issue=int(argv[1]))[
                "repository"
            ]
        except subprocess.CalledProcessError as exc:
            print(exc.stderr.strip(), file=sys.stderr)
            return 1
        print(column_of(repo))
        return 0
    if len(argv) != 2 or not argv[0].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    try:
        move(int(argv[0]), argv[1])
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(getattr(exc, "stderr", "").strip() or exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
