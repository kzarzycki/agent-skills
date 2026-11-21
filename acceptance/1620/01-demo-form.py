#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["pyyaml"]
# ///
"""#1620 Before merge line 2: demo_form takes a fixture PR whose `## Demo` comment links the repo's own sha blob
`?raw=true` (status 0), and refuses one that links another repo's blob (status 1); the script runs each as its own
process and asserts both statuses. Synthetic data, no network."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "gatekeeper", ROOT / "engineering/skills/engineering-loop/scripts/gatekeeper.py"
)
gatekeeper = importlib.util.module_from_spec(SPEC)
sys.modules["gatekeeper"] = gatekeeper
SPEC.loader.exec_module(gatekeeper)

REPO, SHA = "example-owner/example-repo", "0123456789abcdef0123456789abcdef01234567"


def refused(repo: str) -> list[str]:
    body = f"## Demo\n\nthe card.\nhttps://github.com/{repo}/blob/{SHA}/card.png?raw=true\n"
    comment = {"body": body, "author": {"login": "worker"}, "isMinimized": False}
    pull = {
        "number": 1,
        "author": {"login": "worker"},
        "baseRepository": {"nameWithOwner": REPO},
        "comments": {"nodes": [comment]},
    }
    return gatekeeper.demo_form(pull)


REPOS = {"own": REPO, "other": "example-owner/other-repo"}


def main(argv: list[str]) -> int:
    """With `own` or `other`: that fixture's verdict as the exit status, 0 embedded, 1 refused. Without: run each
    fixture as its own process and assert its status, 0 for the repo's own blob and 1 for another repo's."""
    if argv:
        found = refused(REPOS[argv[0]])
        print(f"{argv[0]}:", found or "accepted")
        return 1 if found else 0
    expected = {"own": 0, "other": 1}
    for name, want in expected.items():
        got = subprocess.run([sys.executable, __file__, name], check=False).returncode
        print(f"{name}: exit {got}, want {want}")
        if got != want:
            return 1
    return 0


sys.exit(main(sys.argv[1:]))
