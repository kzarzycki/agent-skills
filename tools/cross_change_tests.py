"""What a Mergify batch runs (`mise run test-batch`): engineering-loop SKILL.md, R6.

    uv run python -m tools.cross_change_tests [--unkeyed-out <file>] [<base>]

stdout is one pytest target per line; `--unkeyed-out` gets one command per line, the checks gatekeeper.md's
`select.unkeyed` lists (gate_plan's unkeyed steps), whose pass is never reused, so every batch runs them. The targets:

- for each PR of the batch, the tests that both its diff and the rest of the merge reach (`targets(diff) ∩
  targets(rest)`), the rest being the base's commits since the PR's branch point plus the other PRs' diffs;
- the floor: every test the diff of a PR with no record for its head's tree reaches, since the cross-change set is
  safe only when each PR's own tests passed on its head. A record is a run of that PR's selected tests: the
  gatekeeper's pass record (`loop-gate/<tree>-<key>`, as narrowed `local-ci --record` pushes it) of loop.md's
  `Affected tests:` command against the PR's branch point, the one `affected-tests --record` pushes on the worker's
  final head, read as `gate-record <head> -- <that command>` reads it.
  A record of the `gate` alone proves no test, so it never counts, and without an `Affected tests:` line no PR has a
  record, so every PR's own tests run.

The PRs are the batch draft's first-parent commits on `base..HEAD`: Mergify builds the draft from `main` with one
`Merge of PR <n>` commit per PR, its second parent the PR's head (seen on this repo's batch drafts). The per-test map
is tools/affected_tests.py's (`.test-map/`, the nightly's). Without one, the batch runs its affected tests (the
fallback, which holds every PR's own tests), and so it does where the commits don't split into PRs; either way one
line says so and why.

It refuses, exit 1 with the reason, when it would run nothing (no unkeyed check, no test) while a PR has no record
or no PR's record can be read: a merge with neither a queue run that ran its selection nor a record per PR. An empty
set where every PR has a record passes and says so. Every line of the selection goes to stderr, prefixed
`cross-change:`, so one batch's log shows it.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tools import affected_tests as a

GATEKEEPER = Path(__file__).resolve().parents[1] / "gatekeeper/skills/gatekeeper/scripts"
MERGE = re.compile(r"Merge of PR (\d+)\b")


class Refused(Exception):
    """The batch would run nothing on a merge some PR of which has no record."""


@dataclass(frozen=True)
class Pull:
    name: str  # `#<n>`, else the merge commit's first 12
    point: str  # the PR's branch point: the merge base of the merge commit's parents
    head: str


def git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def say(line: str) -> None:
    print(f"cross-change: {line}", file=sys.stderr)


def files_between(old: str, new: str) -> list[str]:
    out = git("diff", "--name-only", "--no-renames", old, new)
    return sorted(set(out.split())) if out else []


def pull_requests(base: str) -> list[Pull] | str:
    """Each PR of the batch, or why `base..HEAD` doesn't split into PRs."""
    commits = (git("rev-list", "--first-parent", "--reverse", f"{base}..HEAD") or "").split()
    if not commits:
        return f"no commits on {base}..HEAD"
    pulls = []
    for commit in commits:
        parents = (git("rev-list", "--parents", "-n1", commit) or "").split()[1:]
        if len(parents) != 2:
            return f"{commit[:12]} is not a merge of one PR onto the batch"
        point = git("merge-base", *parents)
        if point is None:
            return f"{commit[:12]}'s parents have no merge base"
        number = MERGE.match(git("log", "-1", "--format=%s", commit) or "")
        pulls.append(Pull(f"#{number[1]}" if number else commit[:12], point, parents[1]))
    return pulls


def gatekeeper():
    sys.path.insert(0, str(GATEKEEPER))
    import approvals

    return approvals


def recorded(head: str, point: str) -> tuple[bool, str]:
    """Whether origin holds the gatekeeper's pass record of loop.md's `Affected tests:` command on `head`'s tree,
    narrowed against `point` (the PR's branch point, the merge base `affected-tests --record` selects against), read
    as `gate-record <head> -- <that command>` reads it; and why. A gatekeeper that fails to answer is no record."""
    g = gatekeeper()
    said = io.StringIO()
    # any failure to read the record (an import, a refusal, git) is no record, said, so the PR's tests run
    try:
        if g.narrowing() is None:
            return (
                False,
                "loop.md has no `Affected tests:` line, so no record of a PR's tests exists",
            )
        with g.narrowed_to(point):
            narrowed = g.narrowed_gate()
        if narrowed is None:
            return False, "the gate has `gate_steps`, which never run the `Affected tests:` command"
        words = [*shlex.split(narrowed[0][: -len(g.NARROWED)]), g.NARROWED.strip()]
        with contextlib.redirect_stdout(said):
            code = g.gate_record(head, words)
    except Exception as exc:  # noqa: BLE001
        return False, f"the record could not be read: {exc}"
    return code == 0, " ".join(said.getvalue().split())[:300]


def unkeyed_checks() -> list[str]:
    """The commands of the gate's steps gatekeeper.md's `select.unkeyed` lists (gate_plan)."""
    return [step["command"] for step in gatekeeper().gate_plan() if step["unkeyed"]]


def select(
    base: str,
    record: Callable[[str, str], tuple[bool, str]] = recorded,
    unkeyed: Callable[[], list[str]] = unkeyed_checks,
) -> tuple[list[str], list[str]]:
    """The batch's unkeyed checks and its test targets; Refused when both are empty and a PR has no record."""
    checks = unkeyed()
    say(f"{len(checks)} unkeyed checks (select.unkeyed){': ' if checks else ''}{'; '.join(checks)}")
    pulls = pull_requests(base)
    if isinstance(pulls, str):
        say(f"fallback to the batch's affected tests: the commits don't split into PRs ({pulls})")
        picked = a.targets(a.changed(base), base)
        if not checks and not picked:
            raise Refused(
                f"nothing to run, and no PR's record can be read since the commits don't split into PRs ({pulls})"
            )
        return checks, picked
    missing = []
    for pull in pulls:
        found, line = record(pull.head, pull.point)
        say(
            f"PR {pull.name} (head {pull.head[:12]}): record {'found' if found else 'none'}: {line}"
        )
        if not found:
            missing.append(pull)
    mapped = a.load_map()
    if mapped is None:
        say(f"fallback to the batch's affected tests: no per-test map at {a.MAP}")
        picked = a.targets(a.changed(base), base)
    else:
        own = {pull: files_between(pull.point, pull.head) for pull in pulls}
        chosen: set[str] = set()
        for pull in pulls:
            rest = sorted(
                set(files_between(pull.point, base)).union(
                    *(f for p, f in own.items() if p != pull)
                )
            )
            both = set(a.targets(own[pull], base)) & set(a.targets(rest, base))
            say(
                f"PR {pull.name}: {len(own[pull])} files, {len(rest)} files of the rest, {len(both)} tests both reach"
            )
            chosen |= both
            if pull in missing:
                floor = set(a.targets(own[pull], base))
                say(
                    f"PR {pull.name}: no record, so its own {len(floor)} affected tests run too (the floor)"
                )
                chosen |= floor
        picked = sorted(chosen)
        say(f"map of {mapped[0][:12]}: {len(picked)} tests")
    if not checks and not picked:
        if missing:
            names = ", ".join(pull.name for pull in missing)
            raise Refused(
                f"nothing to run, and {names} has no record for its head's tree: no test of it ran"
            )
        say("nothing to run: every PR has a record and no test is reached by two changes")
    return checks, picked


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", nargs="?", default="origin/main")
    parser.add_argument("--unkeyed-out", type=Path)
    args = parser.parse_args(argv)
    try:
        checks, targets = select(args.base)
    except Refused as exc:
        say(f"refused: {exc}")
        return 1
    if args.unkeyed_out:
        args.unkeyed_out.write_text("".join(f"{check}\n" for check in checks))
    print("\n".join(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
