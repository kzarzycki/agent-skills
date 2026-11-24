"""The tests a Mergify batch runs (`mise run test-batch`): only the cross-change ones (engineering-loop SKILL.md, R6).

A test that only one PR's diff reaches passed on that PR's head, so it can't fail in the queue because of that PR. The
batch runs, for each PR in it, the tests that both the PR's diff and the rest of the merge reach: the base's commits
since the PR's own branch point, plus the other PRs in the batch. The PRs are the merge commits on the batch's
first-parent line (`base..HEAD`), each PR's diff its second parent's range from the merge base of its parents.

The per-test map is tools/affected_tests.py's (`.test-map/`, the nightly's). Without one, or where the batch's commits
don't split into PRs, it runs the batch's affected tests, today's selection, and says so in one line with the reason.
Every line of the selection goes to stderr, so one batch's log shows it; stdout is one pytest target per line.
"""

from __future__ import annotations

import subprocess
import sys

from tools import affected_tests as a


def git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def say(line: str) -> None:
    print(f"cross-change: {line}", file=sys.stderr)


def files_between(old: str, new: str) -> set[str]:
    out = git("diff", "--name-only", "--no-renames", old, new)
    return set(out.split()) if out else set()


def pull_requests(base: str) -> list[tuple[str, str]] | None:
    """Each PR of the batch as (branch point, head), or None when `base..HEAD` isn't made of merge commits only."""
    commits = (git("rev-list", "--first-parent", "--reverse", f"{base}..HEAD") or "").split()
    prs: list[tuple[str, str]] = []
    for commit in commits:
        parents = (git("rev-list", "--parents", "-n1", commit) or "").split()[1:]
        if len(parents) != 2:
            return None
        point = git("merge-base", *parents)
        if point is None:
            return None
        prs.append((point, parents[1]))
    return prs or None


def select(base: str) -> list[str]:
    files = a.changed(base)
    mapped = a.load_map()
    if mapped is None:
        say(f"fallback to the batch's affected tests: no map at {a.MAP}")
        return a.targets(files, base)
    prs = pull_requests(base)
    if prs is None:
        say("fallback to the batch's affected tests: the batch's commits don't split into PRs")
        return a.targets(files, base)
    own = [files_between(point, head) for point, head in prs]
    picked: set[str] = set()
    for i, (point, _) in enumerate(prs):
        rest = files_between(point, base).union(*(f for j, f in enumerate(own) if j != i))
        both = set(a.targets(sorted(own[i]), base)) & set(a.targets(sorted(rest), base))
        say(
            f"PR {i + 1} of {len(prs)}: {len(own[i])} files, {len(rest)} files of the rest, {len(both)} tests both reach"
        )
        picked |= both
    say(f"map of {mapped[0][:12]}: {len(picked)} tests")
    return sorted(picked)


if __name__ == "__main__":
    print("\n".join(select(sys.argv[1] if len(sys.argv) > 1 else "origin/main")))
