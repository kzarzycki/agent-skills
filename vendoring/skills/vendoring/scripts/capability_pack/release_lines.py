"""The two release lines of `release.yml` (#2678): the decisions its `gate`, `cut` and `promote` jobs make.

`next` is cut after a merge-queue-tested push run on `main` goes green; `stable` is promoted by a green nightly that
ran the full suite. Each decision is a function over data the workflow reads from the event and the forge, so a unit
test covers each case; `main` is the thin command line the workflow calls. Nothing here is read from a fork's text:
the run's fields arrive as JSON in an environment variable, never interpolated into a shell line.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

LINES = {"next": "push", "stable": "schedule"}
_TAG = re.compile(r"(.+)-v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-next)?")


@dataclass(frozen=True)
class Decision:
    ok: bool
    reason: str


def gate(
    run: Mapping, repo: str, line: str, *, tested: bool = False, full_suite: bool = False
) -> Decision:
    """May the CI `run` (a `workflow_run` payload) cut `next` or promote `stable`? Never for a fork's run, a branch
    other than main, the wrong event or a run that is not green; `next` also needs the merge-queue batch to have
    tested the tree, `stable` a nightly that ran the full suite."""
    event = LINES[line]
    head_repo = (run.get("head_repository") or {}).get("full_name")
    if head_repo != repo:
        return Decision(False, f"run is from {head_repo or 'an unknown repository'}, not {repo}")
    if run.get("head_branch") != "main":
        return Decision(False, f"run is on branch {run.get('head_branch')}, not main")
    if run.get("event") != event:
        return Decision(False, f"run's event is {run.get('event')}, {line} takes {event}")
    if run.get("conclusion") != "success":
        return Decision(False, f"run concluded {run.get('conclusion')}, not success")
    if not run.get("head_sha"):
        return Decision(False, "run names no commit")
    if line == "next" and not tested:
        return Decision(False, "no merge-queue batch tested this commit's tree: nothing to release")
    if line == "stable" and not full_suite:
        return Decision(
            False, "this nightly skipped the suite (main had not moved): nothing new to promote"
        )
    return Decision(True, "go")


def full_suite_ran(run_id: int, head_sha: str, green_nightlies: Iterable[Mapping]) -> bool:
    """A green nightly ran the suite unless an earlier green one already ran the same commit (`nightly.py moved
    schedule` skips then, and a skipped run is still green)."""
    return not any(
        other.get("head_sha") == head_sha and int(other["id"]) < run_id for other in green_nightlies
    )


def open_release_pr(pulls: Iterable[Mapping]) -> str | None:
    """The link of an open PR whose head branch is `release/…`, else None."""
    for pull in pulls:
        if pull.get("state", "open") == "open" and str(
            (pull.get("head") or {}).get("ref", "")
        ).startswith("release/"):
            return str(pull.get("html_url") or pull.get("number"))
    return None


def _parse(tag: str):
    match = _TAG.fullmatch(tag)
    if not match:
        return None
    return match.group(1), tuple(int(part) for part in match.groups()[1:4]), bool(match.group(5))


def plan_promotions(
    tags: Mapping[str, str], covered: Callable[[str], bool]
) -> list[tuple[str, str]]:
    """`(stable tag, commit)` for each package: its newest `-next` tag on a commit the nightly covered
    (`covered(commit)`: the nightly's own commit or an ancestor), unless that version or a later one is already
    stable. Older `next` versions in between are skipped."""
    next_tags: dict[str, list[tuple[tuple[int, int, int], str]]] = {}
    stable: dict[str, tuple[int, int, int]] = {}
    for tag, commit in tags.items():
        parsed = _parse(tag)
        if not parsed:
            continue
        package, version, is_next = parsed
        if is_next:
            next_tags.setdefault(package, []).append((version, commit))
        else:
            stable[package] = max(stable.get(package, version), version)
    plan = []
    for package in sorted(next_tags):
        for version, commit in sorted(next_tags[package], reverse=True):
            if not covered(commit):
                continue
            if version > stable.get(package, (-1, 0, 0)):
                plan.append((f"{package}-v{'.'.join(map(str, version))}", commit))
            break
    return plan


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, timeout=120, check=False
    )


def repository_tags(root: Path) -> dict[str, str]:
    """Each tag's commit, annotated or not."""
    out = _git(
        root, "for-each-ref", "refs/tags", "--format=%(refname:short) %(objectname) %(*objectname)"
    )
    tags = {}
    for line in out.stdout.splitlines():
        name, obj, *peeled = line.split()
        tags[name] = peeled[0] if peeled else obj
    return tags


def is_ancestor(root: Path, commit: str, head: str) -> bool:
    return _git(root, "merge-base", "--is-ancestor", commit, head).returncode == 0


def _output(**values: str) -> None:
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
            handle.writelines(f"{key}={value}\n" for key, value in values.items())


def _summary(text: str) -> None:
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as handle:
            handle.write(text + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    verbs = parser.add_subparsers(dest="verb", required=True)
    gate_verb = verbs.add_parser(
        "gate", help="RUN_JSON, REPO in the environment; go=true|false to GITHUB_OUTPUT"
    )
    gate_verb.add_argument("line", choices=tuple(LINES))
    gate_verb.add_argument("--tested", choices=("true", "false"), default="false")
    gate_verb.add_argument(
        "--nightlies", type=Path, help="JSON of the green scheduled runs (stable only)"
    )
    verbs.add_parser("open-pr", help="open release PR among the JSON list on stdin")
    promote = verbs.add_parser(
        "promote", help="print `<stable tag> <commit>` lines for HEAD's covered next tags"
    )
    promote.add_argument("--head", required=True)
    promote.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if args.verb == "gate":
        run = json.loads(os.environ["RUN_JSON"])
        suite = False
        if args.line == "stable":
            green = (
                json.loads(args.nightlies.read_text())["workflow_runs"] if args.nightlies else []
            )
            suite = full_suite_ran(int(run["id"]), run.get("head_sha", ""), green)
        decision = gate(
            run, os.environ["REPO"], args.line, tested=args.tested == "true", full_suite=suite
        )
        _output(
            go=str(decision.ok).lower(), sha=str(run.get("head_sha", "")) if decision.ok else ""
        )
        _summary(
            f"release {args.line}: {'go' if decision.ok else 'nothing released'}: {decision.reason}"
        )
        return 0
    if args.verb == "open-pr":
        # `gh api --paginate` prints one JSON array per page
        text, decoder, at, pulls = sys.stdin.read(), json.JSONDecoder(), 0, []
        while text[at:].strip():
            value, at = decoder.raw_decode(text, len(text) - len(text[at:].lstrip()))
            pulls += value if isinstance(value, list) else [value]
        found = open_release_pr(pulls)
        print(found or "")
        return 0
    for tag, commit in plan_promotions(
        repository_tags(args.root),
        lambda commit: commit == args.head or is_ancestor(args.root, commit, args.head),
    ):
        print(tag, commit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
