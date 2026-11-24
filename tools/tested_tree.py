"""Whether a CI run has anything to run (R7, #2179; #2264): `python3 tools/tested_tree.py push|schedule|tag`.

Reads the forge with the job's token (`GITHUB_TOKEN`, `GITHUB_REPOSITORY`, `GITHUB_API_URL`, `GITHUB_SHA`; the job
needs `actions: read`), never local state, and writes `skip=true|false` to `GITHUB_OUTPUT` and, when it skips, the run
that did the work to the step summary and the log:

- `push`: skip when a successful `pull_request` run of this workflow on a Mergify batch branch
  (`mergify/merge-queue/*`) tested a commit whose tree is the tree of `GITHUB_SHA`.
- `schedule`: skip when the newest successful scheduled run on main ran `GITHUB_SHA` itself ("last green").
- `tag`: skip when any successful scheduled run of `engineering-ci.yml` (the nightly, whose `mise run check` runs
  `test` and `test-slow`) ran `GITHUB_SHA`, the tagged commit. The workflow is named, since this runs in the tag check.

Any API failure reads as "nothing found", so the run goes ahead as before.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections.abc import Callable

BATCH_PREFIX = "mergify/merge-queue/"
NIGHTLY = "engineering-ci.yml"
PAGES = 3
FORGE_ERRORS = (OSError, KeyError, ValueError)  # network and HTTP errors, a missing token, bad JSON

Api = Callable[[str], object]


def github(path: str) -> object:
    request = urllib.request.Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def runs(api: Api, repo: str, workflow: str, query: str) -> list[dict]:
    found: list[dict] = []
    for page in range(1, PAGES + 1):
        batch = api(
            f"/repos/{repo}/actions/workflows/{workflow}/runs?{query}&per_page=100&page={page}"
        )
        items = batch["workflow_runs"]  # type: ignore[index]
        found += items
        if len(items) < 100:
            break
    return found


def tree_of(api: Api, repo: str, sha: str) -> str:
    return api(f"/repos/{repo}/git/commits/{sha}")["tree"]["sha"]  # type: ignore[index]


def tested_by_batch(api: Api, repo: str, workflow: str, sha: str) -> dict | None:
    """The successful batch run that tested the tree of `sha`, else None."""
    tree = tree_of(api, repo, sha)
    for item in runs(api, repo, workflow, "event=pull_request&status=success"):
        if not str(item.get("head_branch", "")).startswith(BATCH_PREFIX):
            continue
        try:
            if tree_of(api, repo, item["head_sha"]) == tree:
                return item
        except (
            FORGE_ERRORS
        ) as error:  # a batch commit the forge no longer holds tested nothing we can read
            print(
                f"tested_tree: batch commit {item['head_sha']} unreadable ({error})",
                file=sys.stderr,
            )
    return None


def last_green_is(api: Api, repo: str, workflow: str, branch: str, sha: str) -> dict | None:
    """The newest successful scheduled run on `branch`, when it ran `sha`, else None."""
    found = api(
        f"/repos/{repo}/actions/workflows/{workflow}/runs?event=schedule&branch={branch}&status=success&per_page=1"
    )["workflow_runs"]  # type: ignore[index]
    if found and found[0]["head_sha"] == sha:
        return found[0]
    return None


def nightly_ran(api: Api, repo: str, workflow: str, sha: str) -> dict | None:
    """A successful scheduled run of `workflow` that ran `sha`, else None."""
    found = api(
        f"/repos/{repo}/actions/workflows/{workflow}/runs?event=schedule&status=success&head_sha={sha}&per_page=1"
    )["workflow_runs"]  # type: ignore[index]
    # the forge filters on head_sha; the check here keeps a filter it ignored from reading as a match
    return next((item for item in found if item["head_sha"] == sha), None)


LINES = {
    "push": (
        "Skipped: this tree was tested by the Mergify batch run ",
        "Running: no batch run tested this tree.",
    ),
    "schedule": (
        "Skipped: main's head is the commit of the last green scheduled run ",
        "Running: main moved since the last green.",
    ),
    "tag": (
        "Skipped test and test-slow: the nightly passed on the tagged commit in ",
        "Running: no green nightly ran the tagged commit.",
    ),
}


def report(mode: str, found: dict | None) -> int:
    skip = found is not None
    line = LINES[mode][0 if skip else 1]
    if skip:
        line += found["html_url"]  # type: ignore[index]
    print(line)
    for name, text in (
        ("GITHUB_OUTPUT", f"skip={'true' if skip else 'false'}"),
        ("GITHUB_STEP_SUMMARY", line),
    ):
        if os.environ.get(name):
            with open(os.environ[name], "a") as handle:
                handle.write(text + "\n")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in LINES:
        print("usage: tested_tree.py push|schedule|tag", file=sys.stderr)
        return 2
    repo, sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    workflow = os.environ.get("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1] or NIGHTLY
    try:
        if argv[0] == "push":
            found = tested_by_batch(github, repo, workflow, sha)
        elif argv[0] == "schedule":
            found = last_green_is(github, repo, workflow, "main", sha)
        else:
            found = nightly_ran(github, repo, NIGHTLY, sha)
    except FORGE_ERRORS as error:
        print(f"tested_tree: forge read failed ({error}); running as usual", file=sys.stderr)
        found = None
    return report(argv[0], found)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
