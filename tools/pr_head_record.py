"""Whether a PR head's tree has a gate pass record: `python3 tools/pr_head_record.py <head-sha>`.

`qualify` runs it on a ready PR so the check that a worker already passed on this tree runs once, not again (engineering-loop
SKILL.md, R1). The record is the gatekeeper's, keyed by tree and command and pushed as `loop-gate/<tree>-<key>`
(`approvals.py gate-record`, the command being the policy's `gate`); the tree is the PR head's, never the test merge commit
GitHub checks out. Writes `recorded=true|false` and `record=<the gatekeeper's line>` to `$GITHUB_OUTPUT`, prints what it
found, and exits 0 whatever it found: a gatekeeper that fails to answer is no record, so the check runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APPROVALS = "gatekeeper/skills/gatekeeper/scripts/approvals.py"


def lookup(head: str) -> tuple[bool, str]:
    """(recorded, the gatekeeper's lines) for `head`'s tree; any failure to ask is (False, why)."""
    try:
        done = subprocess.run(
            ["uv", "run", APPROVALS, "gate-record", head],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"gate-record did not run: {exc}"
    lines = " ".join(done.stdout.split())
    if done.returncode == 0 and lines.startswith("recorded:"):
        return True, lines
    return False, lines or " ".join(done.stderr.split())[
        -300:
    ] or f"gate-record exited {done.returncode}"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: pr_head_record.py <head-sha>", file=sys.stderr)
        return 2
    recorded, line = lookup(argv[0])
    print(f"pass record of the head's tree: {'found' if recorded else 'none'}: {line}")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with Path(output).open("a") as handle:
            handle.write(f"recorded={'true' if recorded else 'false'}\nrecord={line}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
