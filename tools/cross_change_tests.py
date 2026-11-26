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

The PR split, the record read, the unkeyed checks and the refusal are the pack's (`approvals.py queue-select`, which
any project's queue job runs: gatekeeper.py queue_pulls, queue_recorded, queue_unkeyed, queue_refusal); this module
adds only the narrowing to the tests two changes both reach, which needs a per-test map. The PRs are the batch
draft's first-parent commits on `base..HEAD`: Mergify builds the draft from `main` with one `Merge of PR <n>`
commit per PR, its second parent the PR's head (seen on this repo's batch drafts). The per-test map
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
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from tools import affected_tests as a

GATEKEEPER = Path(__file__).resolve().parents[1] / "gatekeeper/skills/gatekeeper/scripts"


class Refused(Exception):
    """The batch would run nothing on a merge some PR of which has no record."""


def say(line: str) -> None:
    print(f"cross-change: {line}", file=sys.stderr)


def files_between(old: str, new: str) -> list[str]:
    done = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", old, new],
        capture_output=True,
        text=True,
        check=False,
    )
    return sorted(set(done.stdout.split())) if done.returncode == 0 else []


def gatekeeper():
    """The pack's gatekeeper, whose `queue-select` is the batch selection any project runs (R6): this module adds only
    the narrowing to the tests two changes both reach, which needs this repo's per-test map."""
    sys.path.insert(0, str(GATEKEEPER))
    import approvals

    return approvals


def recorded(head: str, point: str) -> tuple[bool, str]:
    """The pack's queue_recorded: a pass record of loop.md's `Affected tests:` run on `head`'s tree against `point`."""
    try:
        return gatekeeper().queue_recorded(head, point)
    except Exception as exc:  # noqa: BLE001 -- a gatekeeper that won't load is no record, so the PR's tests run
        return False, f"the record could not be read: {exc}"


def unkeyed_checks() -> list[str]:
    """The pack's queue_unkeyed: the gate's steps gatekeeper.md's `select.unkeyed` lists."""
    return gatekeeper().queue_unkeyed()


def select(
    base: str,
    record: Callable[[str, str], tuple[bool, str]] = recorded,
    unkeyed: Callable[[], list[str]] = unkeyed_checks,
    *,
    pr_head: bool = False,
) -> tuple[list[str], list[str]]:
    """The batch's unkeyed checks and its test targets; Refused when both are empty and a PR has no record.
    `pr_head`: the run is loop.md's `Affected tests:` on a PR head (`check-affected`), not a queue batch. A plain head
    doesn't split into PRs, and an empty selection there is a pass of that PR's selected tests (there are none), so
    it is no refusal and `affected-tests --record` can record it (#2719)."""
    checks = unkeyed()
    say(f"{len(checks)} unkeyed checks (select.unkeyed){': ' if checks else ''}{'; '.join(checks)}")
    g = gatekeeper()
    pulls = g.queue_pulls(base)
    if isinstance(pulls, str):
        say(f"fallback to the batch's affected tests: the commits don't split into PRs ({pulls})")
        picked = a.targets(a.changed(base), base)
        if pr_head and not (checks or picked):
            say("a PR head that reaches no test: nothing to run is a pass of its selected tests")
            return checks, picked
        if why := g.queue_refusal(bool(checks or picked), [], pulls):
            raise Refused(why)
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
    if why := g.queue_refusal(bool(checks or picked), missing):
        raise Refused(why)
    if not checks and not picked:
        say("nothing to run: every PR has a record and no test is reached by two changes")
    return checks, picked


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("base", nargs="?", default="origin/main")
    parser.add_argument("--unkeyed-out", type=Path)
    parser.add_argument(
        "--pr-head",
        action="store_true",
        help="a PR head's `Affected tests:` run (check-affected), not a queue batch: an empty selection passes",
    )
    args = parser.parse_args(argv)
    try:
        checks, targets = select(args.base, pr_head=args.pr_head)
    except Refused as exc:
        say(f"refused: {exc}")
        return 1
    if args.unkeyed_out:
        args.unkeyed_out.write_text("".join(f"{check}\n" for check in checks))
    print("\n".join(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
